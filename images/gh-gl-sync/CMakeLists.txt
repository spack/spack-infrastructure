cmake_minimum_required(VERSION 3.15)
project(SpackCIBridge NONE)
include(CTest)

add_test(
  NAME flake8
  COMMAND flake8 --max-line-length 120 SpackCIBridge.py test_SpackCIBridge.py
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

add_test(
  NAME pytest
  COMMAND pytest --cov=SpackCIBridge --cov-report=xml:bin/coverage.xml
  WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
