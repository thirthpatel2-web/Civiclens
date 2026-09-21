import unittest

from app.data.seed import load_seed, validate
from app.i18n.translator import Translator
from app.services.emergency_service import EmergencyHubService
from app.services.routing_service import DepartmentRouter, RoutingRule
from app.services.classification_service import RuleClassifier


class TranslatorTests(unittest.TestCase):
    tr = Translator.from_files()

    def test_seven_languages_present(self):
        self.assertEqual(self.tr.languages, ["bn", "en", "hi", "kn", "mr", "ta", "te"])

    def test_real_coverage_numbers_are_reported_not_hidden(self):
        cov = self.tr.coverage()
        self.assertEqual((cov["en"]["translated"], cov["en"]["total"]), (142, 142))
        self.assertEqual([cov[l]["translated"] for l in ("hi", "kn")], [140, 140])
        self.assertEqual([cov[l]["translated"] for l in ("ta", "te", "mr", "bn")], [132] * 4)
        self.assertIn("tabInsights", cov["ta"]["missing_keys"])

    def test_translation_and_fallback_tracking(self):
        self.assertEqual({self.tr.t("appName", l) for l in self.tr.languages}, {"CivicLens"})  # brand is never transliterated
        self.assertNotEqual(self.tr.t("tabHome", "hi"), self.tr.t("tabHome", "en"))
        t = Translator.from_files()
        self.assertEqual(t.t("tabInsights", "ta"), t.t("tabInsights", "en"))  # missing in Tamil -> English
        self.assertIn(("ta", "tabInsights"), t.missing)
        self.assertEqual(t.t("no.such.key", "en"), "no.such.key")  # visible, never invented

    def test_language_resolution(self):
        self.assertEqual(self.tr.resolve_language("hi-IN"), "hi")
        self.assertEqual(self.tr.resolve_language("fr"), "en")
        self.assertEqual(self.tr.resolve_language(None), "en")

    def test_placeholders(self):
        t = Translator({"en": {"hello": "Hello {name}, {count} new"}})
        self.assertEqual(t.t("hello", "en", name="Asha", count=3), "Hello Asha, 3 new")
        self.assertEqual(t.t("hello", "en", name="Asha"), "Hello Asha, {count} new")
        with self.assertRaises(ValueError):
            Translator({"hi": {}})

    def test_non_english_scripts_survive_round_trip(self):
        self.assertTrue(any(ord(c) > 0x900 for c in self.tr.t("tabHome", "hi")))
        self.assertTrue(any(ord(c) > 0xB80 for c in self.tr.t("tabHome", "ta")))


class SeedTests(unittest.TestCase):
    def test_seed_is_internally_consistent(self):
        self.assertEqual(validate(load_seed()), [])

    def test_validation_catches_breakage(self):
        s = load_seed()
        s["routing_rules"][0]["department_code"] = "nope"
        s["national_helplines"][0]["number"] = "1x2"
        self.assertEqual(len(validate(s)), 2)

    def test_seeded_rules_route_a_classified_complaint(self):
        seed = load_seed()
        rules = [RoutingRule(r["id"], r["priority"], r["department_code"], categories=frozenset(r["categories"])) for r in seed["routing_rules"]]
        router = DepartmentRouter(rules, frozenset(d["code"] for d in seed["departments"]))
        d = router.route(RuleClassifier().classify("Big pothole on the road"), "Big pothole on the road")
        self.assertEqual((d.department_code, d.source), ("roads", "rule"))

    def test_seed_contains_no_complaints_or_people(self):
        self.assertEqual(set(load_seed()), {"departments", "cities", "routing_rules", "national_helplines", "supported_languages"})


class EmergencyHubTests(unittest.TestCase):
    def setUp(self):
        from tests.support_env import Env

        self.env = Env()
        self.hub = EmergencyHubService(Translator.from_files(), self.env.factory)

    def test_unconfigured_hub_says_so_and_invents_nothing(self):
        r = self.hub.list("en")
        self.assertEqual((r["configured"], r["items"]), (False, []))

    def test_seeding_loads_the_six_source_helplines_once_and_never_overwrites_admin_edits(self):
        self.assertEqual(self.hub.seed_defaults(), 6)
        self.assertEqual(self.hub.seed_defaults(), 0)
        items = self.hub.list("en")["items"]
        self.assertEqual([i["number"] for i in items], ["112", "1930", "1915", "1091", "1098", "1078"])
        self.assertEqual(items[0]["tel_uri"], "tel:112")

    def test_localisation_and_honest_fallback(self):
        self.hub.seed_defaults()
        hi = {i["code"]: i for i in self.hub.list("hi")["items"]}
        self.assertTrue(hi["emergency"]["translated"])
        self.assertNotEqual(hi["emergency"]["name"], "National Emergency")
        self.assertEqual((hi["child"]["language"], hi["child"]["name"], hi["child"]["translated"]), ("en", "Childline Emergency", False))

    def test_inactive_contacts_are_hidden_and_city_scope_filters(self):
        from app.services.ports import EmergencyContactRecord

        with self.env.uow() as u:
            u.emergency.save(EmergencyContactRecord("nat", "112", "National", scope="national"))
            u.emergency.save(EmergencyContactRecord("blr-water", "1916", "Water board", scope="city", city_code="blr"))
            u.emergency.save(EmergencyContactRecord("old", "100", "Old", active=False))
            u.commit()
        self.assertEqual({i["code"] for i in self.hub.list("en")["items"]}, {"nat", "blr-water"})
        self.assertEqual({i["code"] for i in self.hub.list("en", city_code="del")["items"]}, {"nat"})

    def test_contact_validation(self):
        from app.core.exceptions import ValidationFailed
        from app.services.emergency_service import validate_contact
        from app.services.ports import EmergencyContactRecord

        for bad in (EmergencyContactRecord("x", "1-2", "n"), EmergencyContactRecord("Bad Id", "112", "n"), EmergencyContactRecord("ok", "112", ""), EmergencyContactRecord("ok", "112", "n", scope="city")):
            with self.assertRaises(ValidationFailed):
                validate_contact(bad)


if __name__ == "__main__":
    unittest.main()
