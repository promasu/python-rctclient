
# Copyright 2020, Peter Oberhofer (pob90)
# Copyright 2020, Stefan Valouch (svalouch)
# SPDX-License-Identifier: GPL-3.0-only

import logging
import select
import socket
import sys
from typing import List, Optional

try:
    import click
except ImportError:
    print('"click" not found, commands unavailable', file=sys.stderr)
    sys.exit(1)

from .exceptions import FrameCRCMismatch
from .frame import ReceiveFrame, SendFrame
from .registry import REGISTRY as R
from .simulator import run_simulator
from .types import Command
from .utils import decode_value

log = logging.getLogger('rctclient.cli')


@click.group()
@click.pass_context
@click.version_option()
@click.option('-d', '--debug', is_flag=True, default=False, help='Enable debug output')
def cli(ctx, debug: bool) -> None:
    '''
    rctclient toolbox. Please help yourself with the subcommands.
    '''
    ctx.ensure_object(dict)
    ctx.obj['DEBUG'] = debug

    if debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        )
    log.info('rctclient CLI starting')


def autocomplete_registry_name(ctx, args: List, incomplete: str) -> List[str]:
    '''
    Provides autocompletion for the object IDs name parameter.

    :param ctx: Click context (ignored).
    :param args: Arguments (ignored).
    :param incomplete: Incomplete (or empty) string from the user.
    :return: A list of names that either start with `incomplete` or all if `incomplete` is empty.
    '''
    return R.prefix_complete_name(incomplete)


def receive_frame(sock: socket.socket, timeout: int = 2) -> ReceiveFrame:
    '''
    Receives a frame from a socket.

    :param sock: The socket to receive from.
    :param timeout: Receive timeout in seconds.
    :returns: The received frame.
    :raises TimeoutError: If the timeout expired.
    '''
    frame = ReceiveFrame()
    while True:
        try:
            ready_read, _, _ = select.select([sock], [], [], timeout)
        except select.error as e:
            log.error(f'Error during receive: select returned an error: {str(e)}')
            raise

        if ready_read:
            buf = sock.recv(1024)
            if len(buf) > 0:
                log.debug(f'Received {len(buf)} bytes: {buf.hex()}')
                i = frame.consume(buf)
                log.debug(f'Frame consumed {i} bytes')
                if frame.complete():
                    if len(buf) > i:
                        log.warning(f'Frame complete, but buffer still contains {len(buf) - i} bytes')
                        log.debug(f'Leftover bytes: {buf[i:].hex()}')
                    return frame
    raise TimeoutError


@cli.command('read-value')
@click.pass_context
@click.option('-p', '--port', default=8899, type=click.INT, help='Port at which the device listens, default 8899',
              metavar='<port>')
@click.option('-h', '--host', required=True, type=click.STRING, help='Host address or IP of the device',
              metavar='<host>')
@click.option('-i', '--id', type=click.STRING, help='Object ID to query, of the form "0xXXXX"', metavar='<ID>')
@click.option('-n', '--name', help='Object name to query', type=click.STRING, metavar='<name>',
              autocompletion=autocomplete_registry_name)
@click.option('-v', '--verbose', is_flag=True, default=False, help='Enable verbose output')
def read_value(ctx, port: int, host: str, id: Optional[str], name: Optional[str], verbose: bool) -> None:
    '''
    Sends a read request. The request is sent to the target "<host>" on the given "<port>" (default: 8899), the
    response is returned on stdout. Without "verbose" set, the value is returned on standard out, otherwise more
    information about the object is printed with the value.

    Specify either "<id>" or "<name>". The ID must be in the form '0xABCD', the name must exactly match the name of a
    known object ID including the group prefix.

    The "<name>" option supports shell autocompletion (if installed).

    If "debug" is set, log output is sent to stderr, so the value can be read from stdout while still catching
    everything else on stderr.

    Examples:

    \b
    rctclient read-value --name temperature.sink_temp_power_reduction
    rctclient read-value --id 0x90B53336
    \f
    :param ctx: Click context
    :param port: The port number.
    :param host: The hostname or IP address, passed to ``socket.connect``.
    :param id: The ID to query. Mutually exclusive with `name`.
    :param name: The name to query. Mutually exclusive with `id`.
    :param verbose: Prints more information if `True`, or just the value if `False`.
    '''
    if (id is None and name is None) or (id is not None and name is not None):
        log.error('Please specify either --id or --name', err=True)
        sys.exit(1)

    try:
        if id:
            real_id = int(id[2:], 16)
            log.debug(f'Parsed ID: 0x{real_id:X}')
            oinfo = R.get_by_id(real_id)
            log.debug(f'Object info by ID: {oinfo}')
        elif name:
            oinfo = R.get_by_name(name)
            log.debug(f'Object info by name: {oinfo}')
    except KeyError:
        log.error('Could not find requested id or name')
        sys.exit(1)
    except ValueError as e:
        log.debug(f'Invalid --id parameter: {str(e)}')
        log.error('Invalid --id parameter, can\'t parse', err=True)
        sys.exit(1)

    log.debug('Connecting to host')
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        log.debug(f'Connected to {host}:{port}')
    except socket.error as e:
        log.error(f'Could not connect to host: {str(e)}')
        sys.exit(1)

    sframe = SendFrame(command=Command.READ, id=oinfo.object_id)
    sock.send(sframe.data)
    try:
        rframe = receive_frame(sock)
    except FrameCRCMismatch as e:
        log.error(f'Received frame CRC mismatch: received 0x{e.received_crc:X} but calculated 0x{e.calculated_crc:X}')
        sys.exit(1)
    log.debug(f'Got frame: {rframe}')
    if rframe.id != oinfo.object_id:
        log.error(f'Received unexpected frame, ID is 0x{rframe.id:X}, expected 0x{oinfo.object_id:X}')
        sys.exit(1)

    value = decode_value(oinfo.response_data_type, rframe.data)

    if verbose:
        description = oinfo.description if oinfo.description is not None else ''
        unit = oinfo.unit if oinfo.unit is not None else ''
        click.echo(f'#{oinfo.index:3} 0x{oinfo.object_id:8X} {oinfo.name:{R.name_max_length()}} '
                   f'{description:75} {value} {unit}')
    else:
        click.echo(f'{value}')

    try:
        sock.close()
    except Exception as e:
        log.error(f'Exception when disconnecting from the host: {str(e)}')
    sys.exit(0)


@cli.command('simulator')
@click.pass_context
@click.option('-p', '--port', default=8899, type=click.INT, help='Port to bind the simulator to, defaults to 8899',
              metavar='<port>')
@click.option('-h', '--host', default='localhost', type=click.STRING, help='IP to bind the simulator to, defaults to '
              'localhost', metavar='<host>')
@click.option('-v', '--verbose', is_flag=True, default=False, help='Enable verbose output')
def simulator(ctx, port: int, host: str, verbose: bool) -> None:
    '''
    Starts the simulator. The simulator returns valid, but useless responses to queries. It binds to the address and
    port passed using "<host>" (default: localhost) and "<port>" (default: 8899) and allows up to five concurrent
    clients.

    The response values (for read queries) is read from the information associated with the queried object ID if set,
    else a sensible default value (such as 0, False or dummy strings) is computed based on the response data type of
    the object ID.
    \f
    :param port: The port to bind to, defaults to 8899.
    :param host: The address to bind to, defaults to localhost.
    :param verbose: Enables verbose output.
    '''
    if not ctx.obj['DEBUG'] and verbose:
        logging.basicConfig(level=logging.INFO)

    run_simulator(host=host, port=port, verbose=verbose)
