from wsgiref.util import setup_testing_defaults

from wsgissi import parse_command, process, expand_vars, calc_if
from wsgissi import VIRTUAL_CHUNK
from wsgissi import wsgissi


def cmd(command, **kwargs):
    return command, kwargs


def pp(*commands):
    return ''.join(process(commands, '/')[0])


def test_command_parse():
    cmd, args = parse_command('cmd boo="foo" bar="baz"')
    assert cmd == 'cmd'
    assert args == {'boo': 'foo', 'bar': 'baz'}

    cmd, args = parse_command('cmd')
    assert cmd == 'cmd'
    assert args == {}


def test_set_var():
    result = pp(cmd('set', var='boo', value='foo'), cmd('echo', var="boo"))
    assert result == 'foo'

    result = pp(cmd('set', var='boo', value='foo'),
                cmd('set', var='bar', value='$boo&baz'),
                cmd('echo', var='bar'))
    assert result == 'foo&baz'


def test_var_expand():
    assert 'foo&boo' == expand_vars({'bar': 'foo'}, '$bar&boo')
    assert 'fooboo' == expand_vars({'bar': 'foo'}, '${bar}boo')
    assert '$barboo' == expand_vars({'bar': 'foo'}, r'\$barboo')

    assert 'bazfoo&boo' == expand_vars({'bar': 'foo'}, 'baz$bar&boo')
    assert 'bazfooboo' == expand_vars({'bar': 'foo'}, 'baz${bar}boo')
    assert 'baz$barboo' == expand_vars({'bar': 'foo'}, r'baz\$barboo')


def test_virtual():
    content, virtual = process((cmd('set', var='boo', value='baz'),
                                cmd('include', virtual='/foo?bar=$boo')),
                               '/')

    assert content == [VIRTUAL_CHUNK]
    assert virtual == ['/foo?bar=baz']


def test_if_branches():
    result = pp(cmd('if', expr='$boo'),
                ('__content__', 'foo'),
                cmd('endif'))
    assert not result

    result = pp(cmd('set', var='boo', value='1'),
                cmd('if', expr='$boo'),
                ('__content__', 'foo'),
                cmd('endif'))
    assert result == 'foo'

    result = pp(cmd('if', expr='$boo'),
                ('__content__', 'foo'),
                cmd('else'),
                ('__content__', 'boo'),
                cmd('endif'))
    assert result == 'boo'

    result = pp(cmd('set', var='boo', value='1'),
                cmd('if', expr='$foo'),
                ('__content__', 'foo'),
                cmd('elif', expr='$boo'),
                ('__content__', 'boo'),
                cmd('endif'))
    assert result == 'boo'

    result = pp(cmd('if', expr='$foo'),
                ('__content__', 'foo'),
                cmd('elif', expr='$boo'),
                ('__content__', 'boo'),
                cmd('else'),
                ('__content__', 'baz'),
                cmd('endif'))
    assert result == 'baz'


def test_exists_expr():
    assert not calc_if({}, '$foo')
    assert calc_if({'foo': 'foo'}, '$foo')


def test_eq_expr():
    assert calc_if({}, '$foo = ')
    assert not calc_if({}, '$foo = foo')
    assert calc_if({'foo': 'foo'}, '$foo = foo')
    assert not calc_if({'foo': 'foo'}, '$foo = boo')


def test_it_includes_from_virtual():

    def app1(env, sr):
        sr("200 OK", [('Content-Type', 'text/html')])
        return [b'foo <!--# include virtual="bar.html"-->']

    def app2(env, sr):
        sr("200 OK", [('Content-Type', 'text/html')])
        if env['PATH_INFO'] == '/bar.html':
            return [b'bar <!--# include virtual="baz.html"-->']
        elif env['PATH_INFO'] == '/baz.html':
            return [b'baz']
        else:
            assert False, 'Unexpected PATH_INFO %r' % (env['PATH_INFO'])

    app = wsgissi(app1, app2)
    sr = lambda status, headers, exc_info: None
    env = {}
    setup_testing_defaults(env)
    result = b''.join(app(env, sr))
    assert result == b'foo bar baz'
