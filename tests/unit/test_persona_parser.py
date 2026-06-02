"""Tests für den LLM-Output-Parser zum Extrahieren von zwei Personas."""

from __future__ import annotations

from eve.use_cases.onboarding.steps.step_06_personas import _parse_personas

LLM_OUTPUT_REAL_WORLD = """Based on your LinkedIn analytics, here are two distinct synthetic personas:

PERSONA 1
<Role>
Act as a 45-year-old CEO of a mid-sized IT consulting firm (150 employees) based in the Munich
metropolitan area, with 15+ years of professional experience in digital transformation and business
consulting. You're pragmatic, results-driven, and skeptical of hype.

Your goal is to act as a representative of the target audience and provide honest, direct, and emotional
feedback on all marketing and sales initiatives.

In doing so, you evaluate campaigns, advertisements, sales materials, LinkedIn posts, products, and
community events from the perspective of a potential customer.
</Role>

<Organization>
A 150-person IT services and consulting firm in Munich specializing in ERP implementation, cloud
migration, and digital process optimization.
</Organization>

PERSONA 2
<Role>
Act as a 38-year-old founder and co-CEO of a fast-growing SaaS startup (45 employees) based in
Berlin, with strong professional experience in technology and product development.

Your goal is to act as a representative of the target audience and provide honest, direct, and emotional
feedback on all marketing and sales initiatives.
</Role>

<Organization>
A Berlin-based SaaS company in the developer-tooling space.
</Organization>
"""

LLM_OUTPUT_GERMAN = """PERSONA 1
<Role>
Agiere als 50-jährige Geschäftsführerin eines mittelständischen Maschinenbauers (220 Mitarbeitende) im Raum Stuttgart.
</Role>

<Organization>
Mittelständischer Maschinenbauer.
</Organization>

PERSONA 2
<Role>
Agiere als 35-jähriger Co-Founder eines AI-Startups in Berlin.
</Role>

<Organization>
AI-Startup, 12 Mitarbeitende, Seed-Phase.
</Organization>
"""

MALFORMED_OUTPUT = "I'm sorry but I cannot generate that."


def test_parses_two_personas_with_intro():
    personas = _parse_personas(LLM_OUTPUT_REAL_WORLD)
    assert len(personas) == 2

    p1, p2 = personas
    assert "45-year-old CEO" in p1.role
    assert "150-person IT services" in p1.organization

    assert "38-year-old founder" in p2.role
    assert "Berlin-based SaaS" in p2.organization


def test_extracts_german_personas():
    personas = _parse_personas(LLM_OUTPUT_GERMAN)
    assert len(personas) == 2
    assert "Geschäftsführerin" in personas[0].role
    assert "Co-Founder" in personas[1].role


def test_fallback_names_when_no_explicit_name():
    personas = _parse_personas(LLM_OUTPUT_REAL_WORLD)
    # Beide Persona-Texte starten mit "Act as a ..." → kein Eigenname → Fallback greift
    assert personas[0].name in {"Markus", "Lena"}
    assert personas[1].name in {"Markus", "Lena"}
    # Beide sollten unterschiedlich sein (Fallback-Liste hat zwei Einträge)
    assert personas[0].name != personas[1].name


def test_extracts_explicit_name_when_given():
    text = """PERSONA 1
<Role>
Act as Markus, a 45-year-old CFO of a manufacturing company.
</Role>

<Organization>
Manufacturing company.
</Organization>

PERSONA 2
<Role>
Act as Lena, a 35-year-old marketing director.
</Role>

<Organization>
Agency.
</Organization>
"""
    personas = _parse_personas(text)
    assert personas[0].name == "Markus"
    assert personas[1].name == "Lena"


def test_malformed_output_yields_empty_list():
    assert _parse_personas(MALFORMED_OUTPUT) == []


def test_handles_only_one_persona_gracefully():
    text = """PERSONA 1
<Role>
Act as a 50-year-old auditor.
</Role>

<Organization>
Audit firm.
</Organization>
"""
    personas = _parse_personas(text)
    assert len(personas) == 1


# --- Neues Output-Format (kein "Act as"-Prefix, keine Goal-Boilerplate) ----------------

LLM_OUTPUT_NEW_FORMAT = """PERSONA 1
<Role>
Eine 45-jährige Geschäftsführerin eines mittelständischen IT-Beratungshauses
in der Münchner Metropolregion. Du hast 15+ Jahre Berufserfahrung in
digitaler Transformation und bist pragmatisch und ergebnisorientiert.
Du bist skeptisch gegenüber Hype-Themen.
</Role>

<Organization>
Mittelständisches IT-Beratungshaus, 150 Mitarbeitende, München. Fokus auf
ERP-Implementierungen und Cloud-Migrationen für die Industrie.
</Organization>

PERSONA 2
<Role>
Markus, ein 35-jähriger Co-Founder eines wachsenden SaaS-Startups in Berlin.
Du bist technikbegeistert, willst schnell skalieren und scheust auch
unkonventionelle Methoden nicht.
</Role>

<Organization>
SaaS-Startup, 45 Mitarbeitende, Seed-Phase abgeschlossen.
</Organization>
"""


def test_new_format_no_act_as_prefix():
    personas = _parse_personas(LLM_OUTPUT_NEW_FORMAT)
    assert len(personas) == 2

    # Erste Persona: anonym → Fallback-Name
    assert personas[0].name in {"Markus", "Lena"}
    assert personas[0].role.startswith("Eine 45-jährige")
    assert "Mittelständisches IT-Beratungshaus" in personas[0].organization

    # Zweite Persona: hat expliziten Namen "Markus,"
    assert personas[1].name == "Markus"
    assert personas[1].role.startswith("Markus, ein 35-jähriger")


def test_german_persona_with_ist_pattern():
    text = """PERSONA 1
<Role>
Lena ist eine 38-jährige Marketing-Direktorin einer mittelständischen Agentur.
Du legst Wert auf authentische Markenführung.
</Role>

<Organization>
Mittelständische Marketing-Agentur, 60 Mitarbeitende.
</Organization>
"""
    personas = _parse_personas(text)
    assert len(personas) == 1
    assert personas[0].name == "Lena"


def test_no_name_no_false_positive():
    """Ein Persona-Text der mit 'Eine' anfängt darf nicht 'Eine' als Namen extrahieren."""
    text = """PERSONA 1
<Role>
Eine 50-jährige CFO eines Industrieunternehmens.
</Role>

<Organization>
Industriekonzern.
</Organization>
"""
    personas = _parse_personas(text)
    assert len(personas) == 1
    # Fallback greift, weil "Eine" als nicht-Name gefiltert wird
    assert personas[0].name == "Markus"
