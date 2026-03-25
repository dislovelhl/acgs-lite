TEX=acgs_arxiv_skeleton
PDF=$(TEX).pdf
BIB=acgs_refs.bib
MODE?=generic
SUBMISSION?=review

LATEXMK:=$(shell command -v latexmk 2>/dev/null)
TECTONIC:=$(shell command -v tectonic 2>/dev/null)
PDFLATEX:=$(shell command -v pdflatex 2>/dev/null)
BIBTEX:=$(shell command -v bibtex 2>/dev/null)

.PHONY: all pdf bib paper clean distclean check-tools help

all: pdf

pdf: check-tools
ifdef LATEXMK
	latexmk -pdf $(TEX).tex
else ifdef TECTONIC
	tectonic $(TEX).tex
else
	@echo "No supported LaTeX engine found. Install latexmk+pdflatex or tectonic." >&2
	@exit 1
endif

bib:
ifdef LATEXMK
	latexmk -pdf $(TEX).tex
else ifdef PDFLATEX
ifndef BIBTEX
	@echo "bibtex not found. Install bibtex or use latexmk." >&2
	@exit 1
endif
	pdflatex $(TEX).tex
	bibtex $(TEX)
	pdflatex $(TEX).tex
	pdflatex $(TEX).tex
else
	@echo "No supported BibTeX toolchain found." >&2
	@exit 1
endif

paper: check-tools
	bash ./build_paper.sh $(MODE) $(SUBMISSION)

check-tools:
	@echo "Detected tools:"
	@echo "  latexmk : $(if $(LATEXMK),$(LATEXMK),not found)"
	@echo "  tectonic: $(if $(TECTONIC),$(TECTONIC),not found)"
	@echo "  pdflatex: $(if $(PDFLATEX),$(PDFLATEX),not found)"
	@echo "  bibtex  : $(if $(BIBTEX),$(BIBTEX),not found)"

clean:
	rm -f $(TEX).aux $(TEX).bbl $(TEX).blg $(TEX).fdb_latexmk $(TEX).fls $(TEX).log $(TEX).out $(TEX).toc $(TEX).synctex.gz
	rm -f .$(TEX)-*.tex $(TEX)-generic-*.aux $(TEX)-generic-*.bbl $(TEX)-generic-*.blg $(TEX)-generic-*.fdb_latexmk $(TEX)-generic-*.fls $(TEX)-generic-*.log $(TEX)-generic-*.out $(TEX)-generic-*.pdf
	rm -f $(TEX)-neurips-*.aux $(TEX)-neurips-*.bbl $(TEX)-neurips-*.blg $(TEX)-neurips-*.fdb_latexmk $(TEX)-neurips-*.fls $(TEX)-neurips-*.log $(TEX)-neurips-*.out $(TEX)-neurips-*.pdf
	rm -f $(TEX)-icml-*.aux $(TEX)-icml-*.bbl $(TEX)-icml-*.blg $(TEX)-icml-*.fdb_latexmk $(TEX)-icml-*.fls $(TEX)-icml-*.log $(TEX)-icml-*.out $(TEX)-icml-*.pdf


distclean: clean
	rm -f $(PDF)
	rm -rf dist

help:
	@echo "Targets:"
	@echo "  make pdf        Build PDF using latexmk or tectonic"
	@echo "  make bib        Force BibTeX-style build sequence"
	@echo "  make paper MODE=generic|neurips|icml SUBMISSION=review|camera-ready"
	@echo "                  Build venue-specific wrapper PDFs into dist/"
	@echo "  make clean      Remove intermediate files"
	@echo "  make distclean  Remove intermediate files and PDF"
	@echo "  make check-tools  Show detected LaTeX tools"
	@echo ""
	@echo "Venue / camera-ready toggle notes:"
	@echo "  You can either edit toggles near the top of acgs_arxiv_skeleton.tex"
	@echo "  or use: make paper MODE=neurips SUBMISSION=camera-ready"
