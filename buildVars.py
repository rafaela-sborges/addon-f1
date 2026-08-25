# -*- coding: UTF-8 -*-

def _(arg):
	return arg

addon_info = {
	"addon_name": "f1Acessivel",
	"addon_summary": _("Fórmula 1"),
	"addon_description": _("""Mostra a classificação e calendários da Fórmula 1 no NVDA.
Atalhos na lista: P (Pontos), V (Vitórias), E (Equipe/Construtor), D (Data da Corrida)."""),
	"addon_version": "2026.8.23",
	"addon_author": "Rafaela Borges",
	"addon_url": "https://github.com/rafaela/f1-acessivel/",
	"addon_docFileName": "readme.md",
	"addon_minimumNVDAVersion": "2024.1.0",
	"addon_lastTestedNVDAVersion": "2026.1",
	"addon_updateChannel": "stable",
	"addon_license": "GPL 2",
	"addon_licenseURL": "https://www.gnu.org/licenses/gpl-2.0.html",
}

pythonSources = [
	"addon/globalPlugins/f1Acessivel.py",
]

i18nSources = pythonSources + ["buildVars.py"]
excludedFiles = []
baseLanguage = "pt_BR"
markdownExtensions = []
brailleTables = {}
symbolDictionaries = {}
