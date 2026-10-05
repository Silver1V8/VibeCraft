"""Explicit offline migration; unindexed sources do not construct models or clients."""
import argparse

from core.projects import ProjectError, ProjectRegistry
from core.project_migration import migrate_legacy_project


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repair', action='store_true', help='Repair an owned candidate after CURRENT/alias interruption')
    args = parser.parse_args(argv)
    try:
        project = migrate_legacy_project(ProjectRegistry(bootstrap_legacy=False, initialize=False),
                                         repair=args.repair, emit=print)
    except (ProjectError, OSError, RuntimeError) as exc:
        parser.exit(1, f'Migration stopped: {exc}\n')
    print(f'Migrated project {project.id}: {project.root}')


if __name__ == '__main__':
    main()
