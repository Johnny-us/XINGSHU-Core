"""Install built artifacts away from the checkout. This is an offline product check."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import venv


def main():
    artifacts = Path(sys.argv[1]).resolve()
    wheels, sources = list(artifacts.glob('xingshu_core-*.whl')), list(artifacts.glob('xingshu_core-*.tar.gz'))
    if len(wheels) != 1 or len(sources) != 1:
        raise RuntimeError('Expected exactly one wheel and one source distribution')
    for artifact in (wheels[0], sources[0]):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            venv.create(base / 'environment', with_pip=True)
            python = base / 'environment/bin/python'
            subprocess.run([str(python), '-m', 'pip', 'install', str(artifact)], cwd=base, check=True)
            command = [str(python), '-m', 'xingshu_collaboration']
            subprocess.run(command + ['--version'], cwd=base, check=True)
            report = subprocess.run(command + ['doctor'], cwd=base, text=True, capture_output=True)
            if report.returncode != 2 or json.loads(report.stdout)['result']['actual_host_connectivity'] is not False:
                raise RuntimeError('Unbound offline installation must not claim host readiness')
            directory = base / 'machine'
            subprocess.run(command + ['init', '--directory', str(directory)], cwd=base, check=True)
            status = subprocess.run(command + ['status', '--directory', str(directory)], cwd=base, capture_output=True, text=True, check=True)
            if json.loads(status.stdout)['result']['state'] is not None or (directory / 'delivery').exists():
                raise RuntimeError('Status must not create a delivery journal or bind a machine')
            destination, archive = base / '.agents/skills/xingshu-collaborate', base / 'disabled/xingshu-collaborate'
            subprocess.run(command + ['install-skill', '--destination', str(destination)], cwd=base, check=True)
            subprocess.run(command + ['uninstall-skill', '--destination', str(destination), '--archive-directory', str(archive)], cwd=base, check=True)
            if destination.exists() or not (archive / 'SKILL.md').is_file():
                raise RuntimeError('Skill removal must preserve the archived contents')
            subprocess.run([str(python), '-m', 'pip', 'uninstall', '-y', 'xingshu-core'], cwd=base, check=True)
            absent = subprocess.run(command + ['--version'], cwd=base, capture_output=True)
            if absent.returncode == 0:
                raise RuntimeError('Uninstalled package unexpectedly remains importable')
    print('Wheel and source distribution install/uninstall checks passed; real host and second physical machine remain untested.')


if __name__ == '__main__': main()
