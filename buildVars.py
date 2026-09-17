# -*- coding: UTF-8 -*-

def _(arg):
	return arg

addon_info = {
	"addon_name": "f1Acessivel",
	"addon_summary": _("Fórmula 1"),
	"addon_description": _("Mostra a classificação e calendários da Fórmula 1 no NVDA."),
	"addon_version": "2026.9.13",
	"addon_author": "Rafaela Borges <rafaelasouzaborges27@gmail.com>",
	"addon_url": "https://github.com/rafaela-sborges/addon-f1",
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
