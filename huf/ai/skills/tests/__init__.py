import unittest

from .test_skills import (
	TestSkillDestinations,
	TestSkillImportAndExport,
	TestSkillLinkResolution,
	TestSkillManifestParsing,
	TestSkillPromptRuntime,
)


def load_tests(loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: str | None):
	"""Expose all skill tests when running ``huf.ai.skills.tests`` as a module."""
	suite = unittest.TestSuite()
	for test_class in (
		TestSkillManifestParsing,
		TestSkillLinkResolution,
		TestSkillImportAndExport,
		TestSkillPromptRuntime,
		TestSkillDestinations,
	):
		suite.addTests(loader.loadTestsFromTestCase(test_class))
	return suite
