"""Import di progetti esistenti dal filesystem locale in code/<target>/<nome-progetto>
(S5, piano: docs/00_meta_governance/piano_intake_import.md), col pattern plan/apply di
core/indexing.py: il plan è un DRY-RUN puro (zero scritture), l'apply esegue sotto
writer lock.

Il progetto sorgente finisce SEMPRE in una propria sottocartella di code/<target>/,
col nome della cartella sorgente (es. code/backend/GD102_WSGDAProtocolloManager/):
mai spacchettato direttamente dentro code/<target>/, altrimenti le sue cartelle interne
si mischierebbero come fratelli di quelle già presenti nel target.

Semantica NON distruttiva DECISA E VINCOLANTE (decisioni del piano), valutata su
quella sottocartella code/<target>/<nome-progetto>/:
- sottocartella vuota (o inesistente, o di soli .gitkeep) → bootstrap: copia tutto il
  copiabile;
- sottocartella popolata (import ripetuto sullo stesso progetto) → additivo: copia
  SOLO i file nuovi; file esistenti identici per sha256 → skip; file esistenti con
  contenuto diverso → CONFLITTI, riportati nel piano e MAI applicati;
- apply non sovrascrive e non cancella MAI un file esistente in code/;
- nessuna scrittura fuori da code/<target>/ e staging/projects/ (più la riga di journal
  in staging/intake.jsonl, il registro unico dell'intake).

Cosa è "copiabile": i file con estensione in code_index.CODE_EXTS più i file di progetto
riconosciuti per nome (code_index.CODE_FILENAMES, es. pom.xml) — cioè ciò che
l'indicizzazione del codice sa leggere. Le cartelle in CODE_EXCLUDED_DIRS (node_modules,
bin, obj, ...) vengono POTATE alla scansione: compaiono negli esclusi come directory,
senza enumerarne il contenuto (un node_modules reale sono decine di migliaia di file).

Logica pura con DI (pattern di core/intake.py): code_dir/staging/reindex/lock sono
iniettabili; i default risolvono i percorsi reali da core.config a CALL time."""
from __future__ import annotations

import hashlib
import os
import shutil
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from code_index import CODE_EXTS, CODE_FILENAMES
from core.config import CODE_DIR, CODE_EXCLUDED_DIRS, INTAKE_STAGING_DIR, PROJECT_ROOT
from core.intake import _append_journal, ensure_staging_dirs
from core.writer_lock import writer_lock

# Target ammessi: le tre sottocartelle reali di code/ (backend .NET "Portal",
# frontend Next.js, logicAgent). Whitelist chiusa: mai un path libero.
IMPORT_TARGETS = ("backend", "frontend", "logicAgent")


# ---------------------------------------------------------------------------
# Errori tipizzati: lo strato HTTP (api/routes_intake.py) li mappa su status code.
# ---------------------------------------------------------------------------
class ProjectImportError(RuntimeError):
    """Base degli errori dell'import progetti."""


class InvalidImportPathError(ProjectImportError):
    """Path sorgente non valido: relativo, inesistente, non-directory, dentro il
    repo vibecraft o dentro l'area di staging."""


class InvalidImportTargetError(ProjectImportError):
    """Target non tra quelli ammessi (IMPORT_TARGETS)."""


class StaleImportPlanError(ProjectImportError):
    """Lo stato della cartella target è cambiato dopo il plan: ripeti l'anteprima."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_copiable(path: Path) -> bool:
    """File che l'import considera codice: stessa eleggibilità per estensione/nome
    della scansione di code_index (CODE_EXTS + CODE_FILENAMES)."""
    return path.suffix in CODE_EXTS or path.name in CODE_FILENAMES


def _scan_tree(root: Path) -> tuple[list[str], list[str]]:
    """Scansione deterministica di `root`: (copiabili, esclusi) come path relativi
    posix ordinati. Le directory in CODE_EXCLUDED_DIRS sono POTATE (mai attraversate)
    e riportate negli esclusi con il suffisso '/'; i file con estensione non
    riconosciuta finiscono negli esclusi come file."""
    copiabili: list[str] = []
    esclusi: list[str] = []
    if not root.exists():
        return copiabili, esclusi
    for dirpath, dirnames, filenames in os.walk(root):
        base = Path(dirpath)
        for d in sorted(dirnames):
            if d in CODE_EXCLUDED_DIRS:
                esclusi.append((base / d).relative_to(root).as_posix() + "/")
        dirnames[:] = sorted(d for d in dirnames if d not in CODE_EXCLUDED_DIRS)
        for fname in sorted(filenames):
            p = base / fname
            rel = p.relative_to(root).as_posix()
            if _is_copiable(p):
                copiabili.append(rel)
            else:
                esclusi.append(rel)
    return sorted(copiabili), sorted(esclusi)


def _target_fingerprint(target_dir: Path) -> str:
    """Impronta deterministica dello stato ATTUALE della cartella target: sha256 di
    (rel_path, sha256 del contenuto) dei soli file copiabili, in ordine stabile. È il
    guard anti-stale del plan/apply: se fra anteprima e applica compare, sparisce o
    cambia un file rilevante, l'impronta diverge e l'apply rifiuta il piano."""
    h = hashlib.sha256()
    copiabili, _ = _scan_tree(target_dir)
    for rel in copiabili:
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(hashlib.sha256((target_dir / rel).read_bytes()).digest())
    return h.hexdigest()


def _target_is_effectively_empty(target_dir: Path) -> bool:
    """True se la cartella target non esiste o contiene solo .gitkeep: è la soglia
    fra bootstrap (copia tutto) e additivo (solo file nuovi)."""
    if not target_dir.exists():
        return True
    return all(p.name == ".gitkeep" for p in target_dir.rglob("*") if p.is_file())


def _validate_source_path(src_path: str | Path) -> Path:
    """Valida il path sorgente: assoluto, esistente, directory, MAI dentro il repo
    vibecraft né dentro l'area di staging (importare il repo in sé stesso, o lo
    staging, è sempre un errore, non un caso d'uso)."""
    src = Path(src_path)
    if not src.is_absolute():
        raise InvalidImportPathError(f"path non assoluto: {src_path!r}")
    if not src.exists():
        raise InvalidImportPathError(f"path inesistente: {src_path!r}")
    if not src.is_dir():
        raise InvalidImportPathError(f"path non è una directory: {src_path!r}")
    resolved = src.resolve()
    if resolved == PROJECT_ROOT.resolve() or resolved.is_relative_to(PROJECT_ROOT.resolve()):
        raise InvalidImportPathError(
            f"path dentro il repo vibecraft: {src_path!r} — importa solo progetti esterni"
        )
    if resolved.is_relative_to(INTAKE_STAGING_DIR.resolve()):
        raise InvalidImportPathError(
            f"path dentro l'area di staging: {src_path!r} — non importabile"
        )
    return resolved


def _validate_target(target: str) -> str:
    if target not in IMPORT_TARGETS:
        raise InvalidImportTargetError(
            f"target non ammesso: {target!r} (ammessi: {', '.join(IMPORT_TARGETS)})"
        )
    return target


# ---------------------------------------------------------------------------
# ImportPlan: il DRY-RUN serializzabile che viaggia fra plan (anteprima) e apply
# ---------------------------------------------------------------------------
@dataclass
class ImportPlan:
    """Piano deterministico dell'import: modalità, liste per esito e impronta
    anti-stale della cartella target al momento del plan. Serializzabile
    (as_dict/from_dict) perché viaggia attraverso l'API fra anteprima e applica."""
    plan_id: str
    src: str
    target: str
    mode: str  # "bootstrap" | "additivo"
    nuovi: list[str] = field(default_factory=list)
    identici: list[str] = field(default_factory=list)
    conflitti: list[str] = field(default_factory=list)
    esclusi: list[str] = field(default_factory=list)
    fingerprint: str = ""
    created_at: str = ""

    @property
    def totali(self) -> dict:
        return {
            "nuovi": len(self.nuovi),
            "identici": len(self.identici),
            "conflitti": len(self.conflitti),
            "esclusi": len(self.esclusi),
        }

    def as_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "src": self.src,
            "target": self.target,
            "mode": self.mode,
            "nuovi": list(self.nuovi),
            "identici": list(self.identici),
            "conflitti": list(self.conflitti),
            "esclusi": list(self.esclusi),
            "totali": self.totali,
            "fingerprint": self.fingerprint,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ImportPlan":
        try:
            return cls(
                plan_id=str(data["plan_id"]),
                src=str(data["src"]),
                target=str(data["target"]),
                mode=str(data["mode"]),
                nuovi=[str(p) for p in data.get("nuovi", [])],
                identici=[str(p) for p in data.get("identici", [])],
                conflitti=[str(p) for p in data.get("conflitti", [])],
                esclusi=[str(p) for p in data.get("esclusi", [])],
                fingerprint=str(data.get("fingerprint", "")),
                created_at=str(data.get("created_at", "")),
            )
        except (KeyError, TypeError) as exc:
            raise ProjectImportError(f"piano di import malformato: {exc}") from exc


def plan_project_import(src_path: str | Path, target: str, *,
                        code_dir: str | Path | None = None) -> ImportPlan:
    """Anteprima dell'import: scansiona la sorgente (esclusioni CODE_EXCLUDED_DIRS,
    eleggibilità CODE_EXTS/CODE_FILENAMES) e classifica ogni file copiabile contro la
    cartella target: nuovo (assente), identico (stesso sha256), conflitto (contenuto
    diverso — mai applicato). DRY-RUN puro: zero scritture, ovunque."""
    _validate_target(target)
    src = _validate_source_path(src_path)
    code_root = Path(code_dir) if code_dir is not None else CODE_DIR
    target_dir = code_root / target / src.name

    copiabili, esclusi = _scan_tree(src)
    nuovi: list[str] = []
    identici: list[str] = []
    conflitti: list[str] = []
    for rel in copiabili:
        dst = target_dir / rel
        if not dst.exists():
            nuovi.append(rel)
        elif _sha256_file(dst) == _sha256_file(src / rel):
            identici.append(rel)
        else:
            conflitti.append(rel)

    mode = "bootstrap" if _target_is_effectively_empty(target_dir) else "additivo"
    return ImportPlan(
        plan_id=uuid.uuid4().hex[:12],
        src=str(src),
        target=target,
        mode=mode,
        nuovi=nuovi,
        identici=identici,
        conflitti=conflitti,
        esclusi=esclusi,
        fingerprint=_target_fingerprint(target_dir),
        created_at=_now_iso(),
    )


def _backup_target(target_dir: Path, target: str, backups_dir: Path) -> str | None:
    """Backup zip dello stato ATTUALE della cartella target in
    staging/projects/backups/<target>-<timestamp>.zip, PRIMA di qualunque copia.
    Nessun backup se la cartella è vuota (o di soli .gitkeep): non c'è nulla da
    proteggere. Il backup applica le stesse esclusioni della scansione
    (CODE_EXCLUDED_DIRS): un node_modules non si zippa, non è stato scritto da noi
    e renderebbe il backup enorme."""
    if _target_is_effectively_empty(target_dir):
        return None
    backups_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    zip_path = backups_dir / f"{target}-{timestamp}-{uuid.uuid4().hex[:6]}.zip"
    copiabili, esclusi = _scan_tree(target_dir)
    # Nel backup entrano TUTTI i file non potati (anche quelli con estensione non
    # riconosciuta): è una fotografia di sicurezza, non un filtro di indicizzazione.
    members = sorted(set(copiabili) | {e for e in esclusi if not e.endswith("/")})
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in members:
            zf.write(target_dir / rel, arcname=rel)
    return str(zip_path)


def _default_reindex(changed_paths: list[str] | None) -> dict:
    """Reindex delta di default (CLI/uso diretto): import lazy per non pagare torch al
    solo import del modulo (stesso pattern di core/intake.py). Lo strato HTTP inietta
    la variante con le risorse del server (api/routes_intake.py)."""
    from core.indexing import incremental_index
    return incremental_index(changed_paths=changed_paths)


def apply_project_import(plan: ImportPlan | dict, *,
                         code_dir: str | Path | None = None,
                         base_dir: str | Path | None = None,
                         reindex=None,
                         lock_timeout_seconds: float = 30,
                         lock_path: str | Path | None = None) -> dict:
    """Esegue un ImportPlan sotto writer lock: (i) backup zip della cartella target
    attuale (se non vuota di soli .gitkeep, anche in bootstrap); (ii) copia dei SOLI
    file "nuovi" del piano — mai una sovrascrittura, mai una cancellazione; (iii) riga
    nel journal intake.jsonl (target, sorgente, totali, path backup); (iv) reindex
    DELTA del codice (il flusso incrementale di core/indexing.py copre code/: nuovi
    file → nuovi simboli + code-link ricalcolati per i nodi toccati). Se il reindex
    fallisce, i file copiati RESTANO (l'apply è additivo, mai distruttivo) e l'esito
    riporta l'errore con l'avviso esplicito "serve full rebuild per i code-link".

    Anti-stale: se lo stato della cartella target è cambiato dopo il plan (impronta
    diversa da plan.fingerprint), errore "ripeti l'anteprima" PRIMA di ogni scrittura."""
    if isinstance(plan, dict):
        plan = ImportPlan.from_dict(plan)
    _validate_target(plan.target)
    src = _validate_source_path(plan.src)
    code_root = Path(code_dir) if code_dir is not None else CODE_DIR
    target_dir = code_root / plan.target / src.name
    paths = ensure_staging_dirs(base_dir)
    reindex_fn = reindex if reindex is not None else _default_reindex

    with writer_lock(timeout_seconds=lock_timeout_seconds, lock_path=lock_path):
        current_fp = _target_fingerprint(target_dir)
        if current_fp != plan.fingerprint:
            raise StaleImportPlanError(
                f"lo stato di code/{plan.target}/ è cambiato dopo il plan: "
                f"ripeti l'anteprima"
            )

        backup_path = _backup_target(target_dir, plan.target, paths["projects"] / "backups")

        copiati: list[str] = []
        for rel in plan.nuovi:
            dst = target_dir / rel
            if dst.exists():
                # Cintura oltre al fingerprint: mai, in nessun caso, una sovrascrittura.
                raise StaleImportPlanError(
                    f"il file {rel!r} esiste già in code/{plan.target}/: piano stale, "
                    f"ripeti l'anteprima"
                )
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src / rel, dst)
            copiati.append(rel)

        # Delta ristretto ai soli path copiati (repo-relative, come il webhook):
        # possibile solo quando code_dir è quello reale sotto la root del repo.
        # In sandbox (test) si passa None: nessuna restrizione.
        try:
            changed_paths: list[str] | None = [
                (target_dir / rel).resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
                for rel in copiati
            ]
        except ValueError:
            changed_paths = None

        reindex_stats: dict | None = None
        reindex_error: str | None = None
        if copiati:
            try:
                stats = reindex_fn(changed_paths)
                reindex_stats = stats if isinstance(stats, dict) else None
            except Exception as exc:
                # I file copiati restano (additivo, mai distruttivo): l'indice si
                # riallinea col prossimo reindex; l'esito non nasconde nulla.
                reindex_error = f"{type(exc).__name__}: {exc}"

    avviso = ("reindex delta fallito: serve full rebuild per i code-link"
              if reindex_error else None)
    record = {
        "id": f"prj-{uuid.uuid4().hex[:12]}",
        "type": "project_import",
        "status": "applied",
        "target": plan.target,
        "src": plan.src,
        "mode": plan.mode,
        "plan_id": plan.plan_id,
        "applied_at": _now_iso(),
        "totali": {**plan.totali, "copiati": len(copiati)},
        "backup": backup_path,
        "reindex_error": reindex_error,
    }
    _append_journal(paths, record)

    return {
        **record,
        "copiati": copiati,
        "conflitti": plan.conflitti,
        "reindex": reindex_stats,
        "avviso": avviso,
    }
