"""
Dumbo extension package
Flat LangGraph smart-model agent harness for the NOMA / Renglo platform
"""

from setuptools import setup, find_packages

setup(
    name="renglo-dumbo",
    version="1.0.0",
    description="Dumbo — flat LangGraph smart-model agent harness for Renglo",
    author="NOMA Team",
    packages=find_packages(),
    python_requires=">=3.12",
    install_requires=[
        "langgraph>=0.2.0",
        "openai>=1.0.0",
    ],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3.12",
    ],
)
