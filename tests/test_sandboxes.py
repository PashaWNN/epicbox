import time
import uuid
from unittest.mock import ANY
import requests
import docker.errors
import pytest

from epicboxie import config, utils
from epicboxie.exceptions import DockerError
from epicboxie.sandboxes import (create, destroy, run, run_interactive, Communication, working_directory,
                                 _write_files)
from .utils import is_docker_swarm, get_swarm_nodes


def test_create(profile, docker_client):
    test_containers = docker_client.containers.list(
        filters={'name': 'epicbox-test-'}, all=True)
    assert test_containers == []

    sandbox = create(profile.name, 'true')

    container = docker_client.containers.get(sandbox.container.id)
    assert container.name.startswith('epicbox-test-')
    assert container.status == 'created'
    assert 'true' in container.attrs['Args']
    assert sandbox.realtime_limit == 5


def test_create_unknown_image_raises_docker_error_no_such_image(
        profile_unknown_image, config):
    utils._DOCKER_CLIENTS = {}  # clear clients cache
    config.DOCKER_MAX_TOTAL_RETRIES = 0

    with pytest.raises(DockerError) as excinfo:
        create(profile_unknown_image.name)

    error = str(excinfo.value)
    # Error message depends on whether Docker Swarm is used
    assert any(("No such image" in error, "not exist" in error))
    assert 'unknown_image' in error


def test_start_no_stdin_data(profile):
    command = 'echo "stdout data" && echo "stderr data" >&2'
    sandbox = create(profile.name, command)

    with Communication(sandbox) as communication:
        communication.docker_interaction.interact()
    result = communication.results

    expected_result = {
        'exit_code': 0,
        'stdout': b'stdout data\n',
        'stderr': b'stderr data\n',
        'duration': ANY,
        'timeout': False,
        'oom_killed': False,
    }
    assert result == expected_result
    assert result['duration'] > 0


def test_interactive_read(profile):
    command = 'echo "stdout data" && echo "stderr data" >&2'
    sandbox = create(profile.name, command)

    with Communication(sandbox) as communication:
        read_data = communication.docker_interaction.read_sock()
        assert read_data == (b'stdout data\n', b'stderr data\n')

    result = communication.results

    expected_result = {
        'exit_code': 0,
        'stdout': b'stdout data\n',
        'stderr': b'stderr data\n',
        'duration': ANY,
        'timeout': False,
        'oom_killed': False,
    }
    assert result == expected_result


def test_open_ports(profile_networking):
    file = b'from http.server import HTTPServer, BaseHTTPRequestHandler; ' \
           b'HTTPServer(("", 8000), BaseHTTPRequestHandler).serve_forever()'
    files = [{'name': 'main.py', 'content': file}]
    limits = {'realtime': 10, 'memory': 64}
    ports = {8000: 8000}
    with run_interactive(profile_networking.name, 'python3 main.py', files=files, limits=limits, ports=ports) as run:
        time.sleep(2)
        assert requests.get('http://localhost:8000').status_code == 501

    with run_interactive('python', 'python3 main.py', files=files, limits=limits, ports=None) as run:
        time.sleep(2)
        with pytest.raises(requests.ConnectionError):
            requests.get('http://localhost:8000')


def test_interactive_write(profile):
    command = 'python3 -c "print(input()[::-1])"'
    sandbox = create(profile.name, command)

    with Communication(sandbox) as communication:
        communication.docker_interaction.write_sock(b'abcd\n')
        time.sleep(0.2)
        read_data = communication.docker_interaction.read_sock()
        assert read_data == (b'dcba\n', b'')

    result = communication.results

    expected_result = {
        'exit_code': 0,
        'stdout': b'dcba\n',
        'stderr': b'',
        'duration': ANY,
        'timeout': False,
        'oom_killed': False,
    }
    assert result == expected_result
    assert result['duration'] > 0


def test_start_with_stdin_data_bytes(profile):
    sandbox = create(profile.name, 'cat')

    with Communication(sandbox) as communication:
        communication.docker_interaction.interact(stdin=b'stdin data\n')
    result = communication.results

    expected_result = {
        'exit_code': 0,
        'stdout': b'stdin data\n',
        'stderr': b'',
        'duration': ANY,
        'timeout': False,
        'oom_killed': False,
    }
    assert result == expected_result
    assert result['duration'] > 0


def test_start_with_stdin_data_str(profile):
    sandbox = create(profile.name, 'cat')

    with Communication(sandbox) as communication:
        communication.docker_interaction.interact(stdin=b'stdin data\n')
    result = communication.results

    expected_result = {
        'exit_code': 0,
        'stdout': b'stdin data\n',
        'stderr': b'',
        'duration': ANY,
        'timeout': False,
        'oom_killed': False,
    }
    assert result == expected_result
    assert result['duration'] > 0


def test_start_same_sandbox_multiple_times(profile):
    sandbox = create(profile.name, 'cat', limits={'cputime': 20})
    expected_result = {
        'exit_code': 0,
        'stdout': b'',
        'stderr': b'',
        'duration': ANY,
        'timeout': False,
        'oom_killed': False,
    }

    with Communication(sandbox) as communication:
        communication.docker_interaction.interact(timeout=sandbox.realtime_limit)
    result = communication.results
    assert result == expected_result

    with Communication(sandbox) as communication:
        communication.docker_interaction.interact(stdin=b'stdin data')
    result = communication.results
    assert result == dict(expected_result, stdout=b'stdin data')

    long_data = b'stdin long data' + b'a b c d e\n' * 100000
    with Communication(sandbox) as communication:
        communication.docker_interaction.interact(stdin=long_data)
    result = communication.results
    assert result == dict(expected_result, stdout=long_data)

    with Communication(sandbox) as communication:
        communication.docker_interaction.interact()
    result = communication.results
    assert result == expected_result


def test_destroy_not_started(profile, docker_client):
    sandbox = create(profile.name)
    assert docker_client.containers.get(sandbox.container.id)

    destroy(sandbox)

    with pytest.raises(docker.errors.NotFound):
        docker_client.containers.get(sandbox.container.id)


def test_destroy_exited(profile, docker_client):
    sandbox = create(profile.name, 'true')
    with Communication(sandbox) as communication:
        communication.docker_interaction.interact()
    result = communication.results
    assert result['exit_code'] == 0
    assert docker_client.containers.get(sandbox.container.id)

    destroy(sandbox)

    with pytest.raises(docker.errors.NotFound):
        docker_client.containers.get(sandbox.container.id)


def test_destroy_running(profile, docker_client):
    sandbox = create(profile.name, 'sleep 10', limits={'realtime': 1})
    with Communication(sandbox) as communication:
        communication.docker_interaction.interact()
    result = communication.results
    assert result['timeout'] is True
    container = docker_client.containers.get(sandbox.container.id)
    assert container.status == 'running'

    destroy(sandbox)

    with pytest.raises(docker.errors.NotFound):
        docker_client.containers.get(sandbox.container.id)


def test_create_start_destroy_with_context_manager(profile, docker_client):
    with create(profile.name, 'cat') as sandbox:
        with Communication(sandbox) as communication:
            communication.docker_interaction.interact()
        result = communication.results
        assert result['stdout'] == b''

        with Communication(sandbox) as communication:
            communication.docker_interaction.interact(stdin=b'stdin data')
        result = communication.results
        assert result['stdout'] == b'stdin data'

    with pytest.raises(docker.errors.NotFound):
        docker_client.containers.get(sandbox.container.id)


def test_run_python(profile):
    command = ('python3 -c \'import sys; '
               'print("stdout data"); print("stderr data", file=sys.stderr)\'')
    result = run(profile.name, command)

    expected_result = {
        'exit_code': 0,
        'stdout': b'stdout data\n',
        'stderr': b'stderr data\n',
        'duration': ANY,
        'timeout': False,
        'oom_killed': False,
    }
    assert result == expected_result
    assert result['duration'] > 0


def test_run_unknown_profile():
    with pytest.raises(ValueError):
        run('unknown', 'true')


def test_run_invalid_workdir(profile):
    with pytest.raises(ValueError) as excinfo:
        run(profile.name, 'true', workdir='dir')

    assert "working_directory" in str(excinfo.value)


def test_run_non_zero_exit(profile):
    result = run(profile.name, 'false')

    assert result['exit_code'] == 1


def test_run_profile_command(profile):
    result = run(profile.name)

    assert result['exit_code'] == 0
    assert result['stdout'] == b'profile stdout\n'


def test_run_real_timeout(profile):
    result = run(profile.name, 'sleep 100', limits={'realtime': 1})

    assert result['timeout'] is True
    assert result['exit_code'] is None


def test_run_cpu_timeout(profile):
    start_time = time.time()

    result = run(profile.name, 'cat /dev/urandom > /dev/null',
                 limits={'cputime': 1, 'realtime': 10})

    assert result['timeout'] is True
    assert result['exit_code'] is not None
    assert b'Killed' in result['stderr']
    realtime_duration = time.time() - start_time
    assert realtime_duration < 10


def test_run_memory_limit(profile):
    result = run(profile.name, 'python3 -c "[1] * 10 ** 6"',
                 limits={'cputime': 10, 'memory': 8})

    assert result['oom_killed'] is True
    assert result['timeout'] is False
    assert result['exit_code'] not in [None, 0]


def test_run_file_size_limit(profile):
    limits = {'file_size': 10}

    result = run(profile.name, 'echo -n "0123456789" > file', limits=limits)

    assert result['exit_code'] == 0

    result = run(profile.name, 'echo -n "01234567890" > file', limits=limits)

    assert result['exit_code'] == 1
    assert b'write error: File too large' in result['stderr']


def test_run_read_only_file_system(profile_read_only):
    result = run(profile_read_only.name, 'touch /tmp/file')

    assert result['exit_code'] not in [None, 0]
    assert b'Read-only file system' in result['stderr']


def test_fork_exceed_processes_limit(profile):
    result = run(profile.name, 'for x in {0..10}; do sleep 1 & done', limits={'processes': 10})
    assert not result['exit_code']  # forked subprocess fail but main process ok
    assert b"Resource temporarily unavailable" in result['stderr']


def test_fork_in_defaults_processes_limit(profile):
    result = run(profile.name, 'for x in {0..10}; do sleep 1 & done', limits=None)
    assert not result['exit_code']


def test_without_processes_limit(profile):
    result = run(profile.name, 'for x in {0..100}; do sleep 1 & done', limits={'processes': None})
    assert not result['exit_code']
    result = run(profile.name, 'for x in {0..100}; do sleep 1 & done', limits={'processes': -1})
    assert not result['exit_code']


def test_run_network_disabled(profile):
    result = run(profile.name, 'curl -I https://google.com')

    assert result['exit_code']
    assert b'Could not resolve host' in result['stderr']


def test_run_network_enabled(profile):
    profile.network_disabled = False

    result = run(profile.name, 'curl -I https://httpbin.org/status/200',
                 limits={'realtime': 15})

    assert result['exit_code'] == 0
    assert b'200 OK' in result['stdout']


def test_run_upload_files(profile):
    files = [
        {'name': 'main.py', 'content': b'print(open("file.txt").read())'},
        {'name': 'file.txt', 'content': b'Data in file.txt'},
    ]

    result = run(profile.name, 'python3 main.py', files=files)

    assert result['exit_code'] == 0
    assert result['stdout'] == b'Data in file.txt\n'


def test_run_read_stdin(profile):
    result = run(profile.name, 'cat', stdin=b'')

    assert result['exit_code'] == 0
    assert result['stdout'] == b''

    result = run(profile.name, 'cat', stdin=b'binary data\n')

    assert result['exit_code'] == 0
    assert result['stdout'] == b'binary data\n'

    result = run(profile.name, 'cat', stdin='utf8 данные\n')

    assert result['exit_code'] == 0
    assert result['stdout'] == 'utf8 данные\n'.encode()


def test_run_reuse_workdir(profile, docker_client):
    with working_directory() as workdir:
        assert workdir.node is None

        run(profile.name, 'true',
            files=[{'name': 'file', 'content': b'first run data\n'}],
            workdir=workdir)

        if is_docker_swarm(docker_client):
            assert workdir.node

        result = run(profile.name, 'cat file', workdir=workdir)

        assert result['exit_code'] == 0
        assert result['stdout'] == b'first run data\n'


def test_working_directory(docker_client):
    with working_directory() as workdir:
        assert workdir.volume.startswith('epicboxie-')
        node_volume = workdir.volume
        if is_docker_swarm(docker_client):
            node_name = get_swarm_nodes(docker_client)[0]
            node_volume = node_name + '/' + workdir.volume
        volume = docker_client.volumes.get(node_volume)
        assert volume.name == workdir.volume

    with pytest.raises(docker.errors.NotFound):
        docker_client.volumes.get(node_volume)


def test_working_directory_cleanup_on_exception(docker_client):
    with pytest.raises(Exception):
        with working_directory() as workdir:
            volume = docker_client.volumes.get(workdir.volume)
            assert volume.name == workdir.volume

            raise Exception("An error occurred while using a workdir")

    with pytest.raises(docker.errors.NotFound):
        docker_client.volumes.get(workdir.volume)


def test_write_files(docker_client, docker_image):
    command = ('/bin/bash -c '
               '"stat -c %a /sandbox && ls -1 /sandbox && cat /sandbox/*"')
    name = 'epicbox-test-' + str(uuid.uuid4())
    working_dir = config.DOCKER_WORKDIR
    container = docker_client.containers.create(docker_image,
                                                command=command,
                                                name=name,
                                                working_dir=working_dir)
    files = [
        {'name': 'main.py', 'content': b'main.py content'},
        {'name': 'file.txt', 'content': b'file.txt content'},
    ]

    try:
        _write_files(container, files)

        container.start()
        container.wait(timeout=5)
        stdout = container.logs(stdout=True, stderr=False, stream=False)
        assert stdout == (b'755\n'
                          b'file.txt\n'
                          b'main.py\n'
                          b'file.txt contentmain.py content')
    finally:
        container.remove(v=True, force=True)
