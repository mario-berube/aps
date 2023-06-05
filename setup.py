from setuptools import setup

setup(
    name='APS',
    packages=['aps', 'aps.vgosdb', 'aps.schedule', 'aps.utils', 'aps.files'],
    description='Automated Post Solve (APS)',
    version='2.0',
    url='http://github.com/',
    author='Mario',
    author_email='mario.berube@nviinc.com',
    keywords=['vlbi', 'aps'],
    install_requires=['PyQt5'],
    entry_points={
        'console_scripts': [
            'aps=aps.__main__:main',
            'make-config=aps.config:main'
        ]
    },
)
