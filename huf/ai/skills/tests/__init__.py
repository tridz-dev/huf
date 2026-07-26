import unittest


def load_tests(loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: str | None):
	"""Expose all skill tests when running ``huf.ai.skills.tests`` as a module.

	Lazy import avoids pulling in skill exporter/importer classes while the test
	runner is still discovering modules before ``frappe.init`` completes.
	"""
	from .test_skills import (
		TestSkillDestinations,
		TestSkillImportAndExport,
		TestSkillLinkResolution,
		TestSkillManifestParsing,
		TestSkillPromptRuntime,
	)

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
