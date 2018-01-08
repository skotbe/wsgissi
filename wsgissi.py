import logging
import io
import re
import time
try:
    from urllib.parse import urljoin
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urljoin
    from urlparse import urlparse

VIRTUAL_CHUNK = object()
cmd_arg_re = re.compile(r'(\w+)="(.*?)"')
var_re = re.compile(r'(^|[^\\])\$[{]?([_\w]+)[}]?')  # matches $var or ${var}

logger = logging.getLogger(__name__)


def parse_command(command):
    parts = command.split(None, 1)
    if len(parts) > 1:
        cmd, tail = parts
        return cmd, dict(cmd_arg_re.findall(tail))
    else:
        return command, {}


def get_chunks(body):
    end = 0
    start = 0
    while True:
        start = body.find(b'<!--#', end)
        if start < 0:
            yield '__content__', body[end:]
            break
        elif start > end:
            yield '__content__', body[end:start]
        start += 5

        end = body.find(b'-->', start)
        if end < 0:
            break
        command = body[start:end].strip().decode('UTF-8', 'ignore')
        end += 3
        yield parse_command(command)


def expand_vars(ctx, string):
    def sub(match):
        head, var = match.groups()
        return (head or '') + ctx.get(var, '')

    return var_re.sub(sub, string).replace(r'\$', '$')


def calc_if(ctx, expr):
    parts = expr.split()
    if len(parts) == 1:
        return expand_vars(ctx, expr)

    try:
        var, op, value = parts
    except ValueError:
        var, op = parts
        value = ''

    var = expand_vars(ctx, var)
    if op == '=':
        return var == value
    elif op == '!=':
        return var != value


def process(chunks, base):
    ctx = {}
    content = []
    virtual = []
    ifcond = True
    for command, params in chunks:
        if command == 'if':
            ifcond = calc_if(ctx, params['expr'])
            continue
        elif command == 'elif' and not ifcond:
            ifcond = calc_if(ctx, params['expr'])
            continue
        elif command == 'else' and not ifcond:
            ifcond = True
            continue
        elif command == 'endif':
            ifcond = True
            continue

        if not ifcond:
            continue

        if command == '__content__':
            content.append(params)
        elif command == 'include':
            content.append(VIRTUAL_CHUNK)
            virtual.append(urljoin(base, expand_vars(ctx, params['virtual'])))
        elif command == 'set':
            ctx[params['var']] = expand_vars(ctx, params['value'])
        elif command == 'echo':
            content.append(ctx.get(params['var'], ''))

    return content, virtual


def fetch_virtual(env, app, links, log):
    result = []

    environ = {k: v
               for k, v in env.items()
               if (k[:5] == 'HTTP_' or
                   k[:7] == 'SERVER_' or
                   k[:5] == 'wsgi.' or
                   k == 'SCRIPT_NAME')}
    environ['REQUEST_METHOD'] = 'GET'
    environ['wsgi.input'] = io.BytesIO()

    def start_response(status, headers, exc_info=None):
        last_status[0] = status

    for url in links:
        if not isinstance(url, str) and str is bytes:
            url = url.encode('latin1')
        if log:
            logger.info('SSI include %r', url)
        parsed = urlparse(url)
        environ = dict(environ,
                       PATH_INFO=parsed.path,
                       QUERY_STRING=parsed.query
                       )
        last_status = [None]
        st = time.time()
        upstream_content = app(environ, start_response)
        try:
            body = b''.join(upstream_content)
        finally:
            close = getattr(upstream_content, 'close', None)
            if close is not None:
                close()
        duration = time.time() - st
        if log:
            logger.info('%r %r', last_status[0], round(duration * 1000, 3))

        result.append(body)

    return result


def join_content(content, virtual):
    virtual = iter(virtual)
    for c in content:
        if c is VIRTUAL_CHUNK:
            yield next(virtual)
        else:
            yield c


def wsgissi(upstream, downstream=None, log=True, _norecurse=False):
    """
    Wrap a WSGI application in SSI middleware.

    This emulates Nginx SSI directives, including:

    - ``<!--#if ... ><!--# elif ... --><!--# else--><!--# endif -->``
    - ``<!--#set ... >``
    - ``<!--#echo ... >``
    - ``<!--#include ... >``

    :param upstream: WSGI application from which content is read.
    :param downstream: WSGI application which is called to fulfill virtual
                       includes. This may be empty, in which case ``upstream``
                       will be used. Some frameworks (notably fresco) require
                       ``virtual_app`` to be set to the fresco application
                       object in order to set up a new request context for
                       the include requests, ie
                       ``app.add_middleware(wsgissi, app)``
    """
    if downstream is None:
        downstream = upstream

    if not _norecurse:
        downstream = wsgissi(downstream, downstream, log=log, _norecurse=True)

    def inner(env, sr):
        sr_data = []

        def sr_collector(status, headers, exc_info=None):
            sr_data.append((status, headers, exc_info))
            return lambda s: None

        upstream_content = upstream(env, sr_collector)
        try:
            body = b''.join(upstream_content)
        finally:
            close = getattr(upstream_content, 'close', None)
            if close is not None:
                close()
        chunks = get_chunks(body)
        path_info = env['PATH_INFO']
        if path_info == '':
            path = '/'
        else:
            if isinstance(path_info, bytes):
                path = path_info
            else:
                path = env['PATH_INFO'].encode('latin1').decode('utf8')
        content, virtual = process(chunks, path)
        if virtual:
            vcontent = fetch_virtual(env, downstream, virtual, log=log)
        else:
            vcontent = []
        result = b''.join(join_content(content, vcontent))

        status, headers, exc_info = sr_data[0]
        headers = [(h, v) for h, v in headers if h.lower() != 'content-length']
        headers.append(('Content-Length', str(len(result))))

        sr(status, headers, exc_info)
        return [result]

    return inner
