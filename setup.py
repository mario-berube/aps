from setuptools import setup

setup(
    name='APS',
    packages=['aps', 'aps.aps', 'aps.ivsdb', 'aps.vgosdb', 'aps.schedule', 'aps.utils', 'aps.files', 'aps.tools',
              'aps.schedule'],
    description='Automated Post Solve (APS)',
    version='1.4.0',
    url='https://github.com/mario-berube/aps.git',
    author='Mario Berube NVI',
    author_email='mario.berube@nviinc.com',
    keywords=['vlbi', 'aps'],
    install_requires=['PyQt5', 'sqlalchemy', 'sshtunnel', 'toml', 'numpy', 'netCDF4', 'google-api-python-client',
                      'oauth2client', 'pytz', 'beautifulsoup4', 'psutil',
                      'importlib_resources; python_version < "3.9"'],
    package_data={'': ['files/master-format.txt', 'files/ns-codes.txt', 'files/ac-codes.txt', 'files/aps.toml',
                       'files/servers.toml', 'files/types.json', 'files/eops-format.txt']},
    entry_points={
        'console_scripts': [
            'aps=aps.aps.__main__:main'
        ]
    },
)
