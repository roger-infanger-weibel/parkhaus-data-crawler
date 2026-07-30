"""Regelbasierter Chat-Assistent (Deutsch).

Pipeline: preprocess -> entities.extract -> intents.classify -> handlers -> Antwort.

LLM-Austauschbarkeit: engine.ChatEngine ist die Fassade (answer(text, session_id)
-> ChatResponse). Die Handler liefern strukturierte Daten; ein spaeterer
LLMEngine kann dieselben Handler als Tools verwenden und muesste nur
Klassifikation und Textformulierung ersetzen.
"""
