from setuptools import setup, find_packages
import sys, os

version = '0.0'

setup(name='waxe.xml',
      version=version,
      description="",
      long_description="""\
""",
      classifiers=[], # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
      keywords='',
      author='',
      author_email='',
      url='',
      license='MIT',
      packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
      include_package_data=True,
      zip_safe=False,
      namespace_packages=['waxe'],
      install_requires=[
          # -*- Extra requirements: -*-
      ],
      test_suite='nose.collector',
      setup_requires=['nose'],
      tests_require=[
          'nose',
          'nose-cov',
          'WebTest',
          'mock',
      ],
      entry_points="""
      # -*- Entry points: -*-
      """,
      )
