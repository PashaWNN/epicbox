import pytest

from epicboxie.utils import DockerInteraction


def test_docker_communicate_empty_input_empty_output(test_utils):
    container = test_utils.create_test_container(command='true')

    with DockerInteraction(container) as interaction:
        interaction.interact()
    stdout, stderr = interaction.output_streams

    assert stdout == b''
    assert stderr == b''


def test_docker_communicate_empty_input_closed_stdin(test_utils):
    container = test_utils.create_test_container(command='cat',
                                                 stdin_open=False)

    with DockerInteraction(container) as interaction:
        interaction.interact()
    stdout, stderr = interaction.output_streams

    assert stdout == b''
    assert stderr == b''


def test_docker_communicate_only_output(test_utils):
    container = test_utils.create_test_container(command='echo 42')

    with DockerInteraction(container) as interaction:
        interaction.interact()
    stdout, stderr = interaction.output_streams

    assert stdout == b'42\n'
    assert stderr == b''


def test_docker_communicate_split_output_streams(test_utils):
    container = test_utils.create_test_container(
        command='/bin/sh -c "cat && echo error >&2"')

    with DockerInteraction(container) as interaction:
        interaction.interact(stdin=b'42\n')
    stdout, stderr = interaction.output_streams

    assert stdout == b'42\n'
    assert stderr == b'error\n'


def test_docker_communicate_copy_input_to_output(test_utils):
    stdin_options = [
        b'\n\n\r\n',
        b'Hello!',
        b'Hello!\n',
        b'0123456789' * 100000,
    ]
    for stdin in stdin_options:
        container = test_utils.create_test_container(command='cat')

        with DockerInteraction(container) as interaction:
            interaction.interact(stdin=stdin)
        stdout, stderr = interaction.output_streams

        assert stdout == stdin
        assert stderr == b''


def test_docker_communicate_failed_command(test_utils):
    container = test_utils.create_test_container(command='sleep')

    with DockerInteraction(container) as interaction:
        interaction.interact()
    stdout, stderr = interaction.output_streams

    assert stdout == b''
    assert b'missing operand' in stderr


def test_docker_communicate_timeout_reached(test_utils, docker_client):
    container = test_utils.create_test_container(
        command='/bin/sh -c "echo 42 && sleep 30"')

    with pytest.raises(TimeoutError):
        with DockerInteraction(container) as interaction:
            interaction.interact(timeout=1)

    container.reload()
    assert container.status == 'running'
