from setuptools import setup, find_packages

setup(
    name='shrooly_cli',
    version='1.2',
    url="https://github.com/shrooly/shrooly-cli",
    author='Adam Lipecz',
    author_email='developer@shrooly.com',
    packages=find_packages(),
    install_requires=[
        'pyserial',
        'pyyaml',
        'colorlog',
        'pillow'
    ],
)