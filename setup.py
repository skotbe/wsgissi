from setuptools import setup
import io

setup(
    name='wsgissi-skot',
    version='0.9.dev0',
    url='https://github.com/skotbe/wsgissi/',
    license='MIT',
    author='Olly Cope',
    author_email='oliver@redgecko.org',
    description='WSGI middleware to process nginx compatible ssi',
    long_description=io.open('README.rst', encoding="utf-8").read(),
    py_modules=['wsgissi'],
    install_requires=[],
    include_package_data=True,
    zip_safe=False,
    keywords='nginx, ssi, wsgi, middleware',
    platforms='any',
    classifiers=[
        'Development Status :: 4 - Beta',
        # 'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Intended Audience :: Information Technology',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: MIT License',
        'Operating System :: POSIX',
        'Operating System :: MacOS',
        'Operating System :: Unix',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 3',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: Internet',
        'Topic :: Scientific/Engineering',
        'Topic :: System :: Distributed Computing',
        'Topic :: System :: Systems Administration',
        'Topic :: System :: Monitoring',
    ]
)
