from setuptools import setup, find_packages
import sys, os

version = '0.0'

setup(name='nginx_configuration_fs',
      version=version,
      description="",
      long_description="""\
""",
      classifiers=[], # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
      keywords='',
      author='',
      author_email='',
      url='',
      license='',
      packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
      include_package_data=True,
      zip_safe=False,
      install_requires=[
          # -*- Extra requirements: -*-
          'fusepy==2.0.1',
          'colorama==0.2.4',
          'plone.synchronize==1.0.1',
          'plone.memoize==1.1.1',
          'dnspython==1.11.1',
          'pyinotify==0.9.4',
          'jinja2==2.6',
          'pyOpenSSL==0.13',
          'regex==0.1.20121216',
          'rfc3987==1.3.1',
          'plac==0.9.1',
          'twisted==13.0.0',
          'jsonschema==2.0.0',
          'stringlike==0.3.2',
      ],
      entry_points="""
      # -*- Entry points: -*-
      """,
      )
