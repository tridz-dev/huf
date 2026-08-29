# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Real-Frappe (Layer B) integration tests for the Automation runtime
described in ``docs/testing/CURRENT_STATE.md`` section 7 ("Automations").

Covers the CURRENT DEFAULT active runtime only (Automation / Automation
Trigger / ``automation_scheduler.py`` — confirmed default "new" via
``huf/ai/automation_runtime_flag.py::automation_runtime_is_new()``, which
returns True unless ``site_config.json`` explicitly sets
``automation_trigger_runtime: "legacy"``). The legacy ``Agent Trigger`` /
``agent_scheduler.py`` path is not exercised here — see AUTO-007 note below
for why the doc-event legacy/new distinction was skipped entirely for this
file.

Every fixture created by this file is prefixed "_Test P51 Automation" so it
cannot collide with fixtures created by another concurrent test file
sharing the same site/bench.

Time-sensitive assertions (AUTO-002/003/004) use
``huf.ai.tests.clock_helpers.FakeClock``/``patch_clock`` patched onto
``huf.ai.automation_scheduler``'s own ``now_datetime``/``add_to_date``
names (the exact pattern already proven working in
``huf/ai/tests/test_automation_scheduler_clock.py``, a from-import module).
No ``time.sleep()`` anywhere in this file.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.tests.test_automation_p0
"""

import datetime

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai import automation_scheduler
from huf.ai.automation_runner import _check_run_as_user_permission, run_automation
from huf.ai.tests.clock_helpers import patch_clock
from huf.ai.tests.factories import (
    make_agent,
    make_ai_model,
    make_ai_provider,
    make_automation,
    make_automation_trigger,
    make_user,
)

PREFIX = "_Test P51 Automation"


class TestAutomationP0(IntegrationTestCase):
    def setUp(self):
        self._names = {
            "Automation Trigger": [],
            "Automation": [],
            "Agent Conversation": [],
            "Agent": [],
            "AI Model": [],
            "AI Provider": [],
            "User": [],
        }

    def tearDown(self):
        frappe.set_user("Administrator")
        for doctype in (
            "Automation Trigger",
            "Automation",
            "Agent Conversation",
            "Agent",
            "AI Model",
            "AI Provider",
            "User",
        ):
            for name in self._names.get(doctype, []):
                self._delete(doctype, name)
        frappe.db.commit()

    def _delete(self, doctype, name):
        try:
            frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
        except Exception:
            pass

    def _track(self, doctype, name):
        self._names.setdefault(doctype, []).append(name)
        return name

    def _make_test_provider_agent(self, **agent_overrides):
        """Create an Agent wired to the HUF Test Provider.

        Reuses the exact idempotent get-or-create pattern established in
        ``huf/ai/tests/test_agent_runtime_p0.py::_make_test_provider_agent``
        — the AI Provider document's ``name`` MUST be exactly
        "Test_Provider" (case-insensitive exact match, not a prefix) for
        ``litellm.run()``'s routing check (``provider.lower() ==
        "test_provider"``) to fire. A hash-suffixed name silently falls
        through to a real (failing) litellm call instead — deliberately not
        repeating that mistake here.
        """
        if frappe.db.exists("AI Provider", "Test_Provider"):
            provider = frappe.get_doc("AI Provider", "Test_Provider")
        else:
            provider = make_ai_provider(provider_name="Test_Provider")
            self._track("AI Provider", provider.name)
        model = make_ai_model(
            provider=provider.name, model_name=f"test-model-{frappe.generate_hash(length=6)}"
        )
        self._track("AI Model", model.name)

        agent_overrides.setdefault("agent_name", f"{PREFIX} Agent {frappe.generate_hash(length=8)}")
        agent = make_agent(provider=provider.name, model=model.name, **agent_overrides)
        self._track("Agent", agent.name)
        return agent

    def _make_automation(self, agent, **overrides):
        overrides.setdefault("automation_name", f"{PREFIX} {frappe.generate_hash(length=8)}")
        overrides.setdefault("instruction", "__TEST_SCENARIO__:TEST_TEXT")
        # `Automation.status` defaults to "Draft" (make_automation()'s own
        # docstring), but automation_runner.py::run_automation now refuses
        # to fire a non-"Active" Automation ("... is not Active (status:
        # Draft) -- resume it to let triggers run."), added alongside this
        # merge's automation-lifecycle work. Every test in this file submits
        # a real trigger fire and asserts on its outcome, so it needs a
        # runnable (Active) Automation by default, same as
        # `_make_test_provider_agent()` above always returns a runnable
        # Agent rather than a minimal-but-inert one.
        overrides.setdefault("status", "Active")
        automation = make_automation(agent=agent.name, **overrides)
        self._track("Automation", automation.name)
        return automation

    def _make_trigger(self, automation, **overrides):
        overrides.setdefault("trigger_name", f"{PREFIX} Trigger {frappe.generate_hash(length=8)}")
        trigger = make_automation_trigger(automation=automation.name, **overrides)
        self._track("Automation Trigger", trigger.name)
        return trigger

    def _agent_run_count(self, agent_name):
        return frappe.db.count("Agent Run", {"agent": agent_name})

    # -- AUTO-001 -----------------------------------------------------

    def test_auto_001_automation_trigger_round_trips_via_reload(self):
        """Create an Automation Trigger (Schedule type) targeting a
        Test-Provider-wired Agent, verify every field round-trips via a
        fresh ``.reload()``/re-fetch from the DB — not just the in-memory
        object returned by ``.insert()``."""
        agent = self._make_test_provider_agent()
        # This test asserts the doctype's own persisted default (Draft),
        # not a fired run, so it opts out of the Active default the other
        # tests in this file need — see _make_automation()'s comment.
        automation = self._make_automation(agent, status="Draft")

        next_execution = frappe.utils.now_datetime().replace(microsecond=0)
        trigger = self._make_trigger(
            automation,
            trigger_type="Schedule",
            scheduled_interval="Daily",
            interval_count=1,
            next_execution=next_execution,
            disabled=0,
        )

        # Round-trip: reload the in-memory doc AND re-fetch a brand new doc
        # instance by name, so this doesn't just prove the same Python
        # object still holds what we set.
        trigger.reload()
        reloaded = frappe.get_doc("Automation Trigger", trigger.name)

        self.assertEqual(reloaded.automation, automation.name)
        self.assertEqual(reloaded.trigger_type, "Schedule")
        self.assertEqual(reloaded.scheduled_interval, "Daily")
        self.assertEqual(reloaded.interval_count, 1)
        self.assertEqual(reloaded.disabled, 0)
        self.assertEqual(reloaded.next_execution, next_execution)

        automation.reload()
        self.assertEqual(automation.agent, agent.name)
        self.assertEqual(automation.status, "Draft")

    # -- AUTO-002 -----------------------------------------------------

    def test_auto_002_due_check_fires_when_past_and_skips_when_future(self):
        """current time -> due automation -> scheduler decision (fires),
        and current time -> NOT due -> scheduler decision (skips) — both
        via the real whitelisted entrypoint ``run_due_automations()``
        (not just the inner ``_fire_due_trigger``), under a fake clock
        patched onto ``automation_scheduler``'s own ``now_datetime``/
        ``add_to_date`` names."""
        with patch_clock(automation_scheduler, initial="2026-01-01 12:00:00") as clock:
            agent = self._make_test_provider_agent()
            automation = self._make_automation(agent)

            past_next_execution = clock.now_datetime() - datetime.timedelta(hours=1)
            due_trigger = self._make_trigger(
                automation,
                trigger_type="Schedule",
                scheduled_interval="Daily",
                interval_count=1,
                next_execution=past_next_execution,
                disabled=0,
            )

            before = self._agent_run_count(agent.name)
            automation_scheduler.run_due_automations()
            after_due = self._agent_run_count(agent.name)
            self.assertEqual(
                after_due - before, 1, "a past-due Schedule trigger must fire exactly once"
            )

            # The due trigger's next_execution must have been advanced
            # forward (past "now") so it doesn't re-fire on the next tick.
            due_trigger.reload()
            self.assertGreater(due_trigger.next_execution, clock.now_datetime())

            # A second trigger whose next_execution is in the future must
            # NOT fire on this same tick.
            future_trigger = self._make_trigger(
                automation,
                trigger_type="Schedule",
                scheduled_interval="Daily",
                interval_count=1,
                next_execution=clock.now_datetime() + datetime.timedelta(hours=1),
                disabled=0,
            )
            before_future = self._agent_run_count(agent.name)
            automation_scheduler.run_due_automations()
            after_future = self._agent_run_count(agent.name)
            self.assertEqual(
                after_future,
                before_future,
                "a not-yet-due Schedule trigger must not fire",
            )
            future_trigger.reload()
            self.assertEqual(
                future_trigger.next_execution,
                clock.now_datetime() + datetime.timedelta(hours=1),
                "an unfired trigger's next_execution must be untouched",
            )

    # -- AUTO-003 -----------------------------------------------------

    def test_auto_003_disabled_trigger_and_disabled_automation_never_execute(self):
        """A disabled Automation Trigger is excluded by
        ``run_due_automations()``'s own query filter (``disabled: 0``) even
        when its ``next_execution`` is due — and a disabled Automation
        itself is rejected by ``run_automation()``'s explicit
        ``automation.disabled`` guard even when invoked directly."""
        with patch_clock(automation_scheduler, initial="2026-01-01 12:00:00") as clock:
            agent = self._make_test_provider_agent()
            automation = self._make_automation(agent)

            self._make_trigger(
                automation,
                trigger_type="Schedule",
                scheduled_interval="Daily",
                interval_count=1,
                next_execution=clock.now_datetime() - datetime.timedelta(hours=1),
                disabled=1,  # disabled — must never fire even though due
            )

            before = self._agent_run_count(agent.name)
            automation_scheduler.run_due_automations()
            after = self._agent_run_count(agent.name)
            self.assertEqual(after, before, "a disabled trigger must never execute")

        # Disabled Automation itself: run_automation() must refuse to run it
        # even via a direct, non-scheduler call (e.g. "Run now"/manual path).
        automation.db_set("disabled", 1, update_modified=False)
        automation.reload()
        self.assertTrue(automation.disabled)

        before_disabled_automation = self._agent_run_count(agent.name)
        with self.assertRaises(frappe.ValidationError):
            run_automation(automation.name, now=True)
        after_disabled_automation = self._agent_run_count(agent.name)
        self.assertEqual(
            after_disabled_automation,
            before_disabled_automation,
            "a disabled Automation must never execute, even via a direct run_automation() call",
        )

    # -- AUTO-004 -----------------------------------------------------

    def test_auto_004_overlapping_ticks_fire_only_once(self):
        """Duplicate-execution prevention (GOAL.md section 27 P0 acceptance
        criterion): the 60s-TTL cache-lock per due trigger in
        ``automation_scheduler._fire_due_trigger`` must ensure two
        overlapping scheduler ticks racing the SAME due trigger snapshot
        (as would happen if two ticks both queried before either advanced
        ``next_execution``) result in exactly ONE actual execution.

        Calls ``_fire_due_trigger`` directly (not the outer
        ``run_due_automations()``) with an identical trigger dict twice in
        immediate succession, precisely simulating that stale-batch-query
        race — this is the real ``frappe.cache()``-backed lock on this
        bench (real Redis), not a mock, so this is a genuine exercise of
        the lock, not merely an assertion about the provisional
        next_execution advance (which alone would also prevent a *third*
        tick from re-matching the query, but does not by itself prove the
        lock guards the overlapping-race window between two ticks sharing
        one stale snapshot).
        """
        with patch_clock(automation_scheduler, initial="2026-01-01 12:00:00") as clock:
            agent = self._make_test_provider_agent()
            automation = self._make_automation(agent)

            now = clock.now_datetime()
            past_next_execution = now - datetime.timedelta(hours=1)
            trigger = self._make_trigger(
                automation,
                trigger_type="Schedule",
                scheduled_interval="Daily",
                interval_count=1,
                next_execution=past_next_execution,
                disabled=0,
            )

            trigger_dict = {
                "name": trigger.name,
                "automation": automation.name,
                "scheduled_interval": "Daily",
                "interval_count": 1,
                "next_execution": past_next_execution,
                "last_execution": None,
            }

            before = self._agent_run_count(agent.name)
            # Two overlapping ticks, same stale trigger snapshot, no real
            # sleep in between — exactly the race the lock exists for.
            automation_scheduler._fire_due_trigger(trigger_dict, now)
            automation_scheduler._fire_due_trigger(trigger_dict, now)
            after = self._agent_run_count(agent.name)

            self.assertEqual(
                after - before,
                1,
                "two overlapping ticks racing the same due trigger must "
                "execute it exactly once, not twice — UNVERIFIED only in "
                "the sense that this assumes a real Redis-backed "
                "frappe.cache() on this bench; if cache() falls back to a "
                "non-shared/no-op backend in the test process, this "
                "assertion would falsely pass by starving on that, not on "
                "the lock — coordinator should confirm frappe.cache() is "
                "real Redis in the run-tests environment.",
            )

    # -- AUTO-005 -----------------------------------------------------

    def test_auto_005_run_as_user_permission_gated_to_system_manager(self):
        """``_check_run_as_user_permission`` must reject an Automation
        configured to run as a *different* user than its owner unless that
        owner holds the System Manager role — and must allow it once the
        owner does."""
        agent = self._make_test_provider_agent()
        automation = self._make_automation(agent)

        non_manager = make_user(
            email=f"huf-p51-nonmgr-{frappe.generate_hash(length=8)}@example.com",
            roles=("Huf User",),
        )
        self._track("User", non_manager.name)
        other_user = make_user(
            email=f"huf-p51-other-{frappe.generate_hash(length=8)}@example.com",
            roles=("Huf User",),
        )
        self._track("User", other_user.name)

        # Non-System-Manager owner attempting to run the automation as a
        # different user must be rejected.
        automation.owner = non_manager.name
        automation.run_as_user = other_user.name
        with self.assertRaises(frappe.PermissionError):
            _check_run_as_user_permission(automation)

        # Same configuration, but the owner now holds System Manager ->
        # must succeed (no exception).
        system_manager_user = make_user(
            email=f"huf-p51-sysmgr-{frappe.generate_hash(length=8)}@example.com",
            roles=("Huf User", "System Manager"),
        )
        self._track("User", system_manager_user.name)

        automation.owner = system_manager_user.name
        automation.run_as_user = other_user.name
        try:
            _check_run_as_user_permission(automation)
        except frappe.PermissionError:
            self.fail("System Manager owner must be allowed to set run_as_user to another user")

        # Sanity: run_as_user == owner is always a no-op (never impersonation).
        automation.owner = non_manager.name
        automation.run_as_user = non_manager.name
        try:
            _check_run_as_user_permission(automation)
        except frappe.PermissionError:
            self.fail("run_as_user == owner must never be treated as impersonation")

    # -- AUTO-006 -----------------------------------------------------

    def test_auto_006_system_agent_lock_blocks_non_system_manager_edit(self):
        """``Automation._validate_system_agent_lock()`` (the doctype
        controller's own ``validate()`` guard, not just the API-layer
        wrapper) must block a non-System-Manager user — even one holding
        "Huf Manager" (which DOES have doctype-level write/create
        permission on Automation per its own permissions block) — from
        saving an edit to an Automation that targets a locked system
        agent. A System Manager editing the same Automation must succeed."""
        system_agent = self._make_test_provider_agent(is_system=1)
        self.assertTrue(
            frappe.db.get_value("Agent", system_agent.name, "is_system"),
            "fixture setup: system_agent must actually be flagged is_system=1",
        )

        automation = self._make_automation(system_agent)

        huf_manager = make_user(
            email=f"huf-p51-hufmgr-{frappe.generate_hash(length=8)}@example.com",
            roles=("Huf Manager",),
        )
        self._track("User", huf_manager.name)
        self.assertNotIn(
            "System Manager",
            frappe.get_roles(huf_manager.name),
            "fixture setup: huf_manager must NOT hold System Manager",
        )

        frappe.set_user(huf_manager.name)
        try:
            doc = frappe.get_doc("Automation", automation.name)
            doc.description = "edited by non-system-manager Huf Manager"
            with self.assertRaises(frappe.PermissionError):
                doc.save()
        finally:
            frappe.set_user("Administrator")

        # Confirm the edit truly did not persist.
        automation.reload()
        self.assertNotEqual(automation.description, "edited by non-system-manager Huf Manager")

        # A System Manager (Administrator) editing the same Automation must
        # succeed — proving the guard is role-gated, not a blanket lock.
        doc = frappe.get_doc("Automation", automation.name)
        doc.description = "edited by System Manager"
        doc.save()
        doc.reload()
        self.assertEqual(doc.description, "edited by System Manager")

    # -- AUTO-007 -----------------------------------------------------
    #
    # SKIPPED: doc-event trigger routing (huf/ai/automation_hooks.py's
    # run_hooked_automations) queues work via frappe.db.after_commit.add(...)
    # + huf.utils.background_jobs.enqueue(...) onto a real RQ "long" queue —
    # there is no synchronous, in-process call this test could invoke that
    # both (a) exercises the real hook-registration/condition/routing path
    # and (b) completes deterministically without a running bench worker to
    # drain that queue. Faking it out (calling run_automation_for_doc
    # directly, bypassing after_commit/enqueue) would mostly just be
    # re-testing run_automation() again, not the actual doc-event routing
    # this test is meant to cover. Per this task's explicit instruction to
    # skip AUTO-007 rather than force a low-confidence test, it is omitted
    # here. UNVERIFIED - coordinator must confirm on real bench (with a
    # worker draining the "long" queue, or by capturing the enqueue() call
    # args and asserting on job_id/kwargs shape instead of end-to-end
    # execution) whether doc-event Automation Triggers actually fire
    # end-to-end in the live environment.
