.PHONY: build

all: build



build:
	@latexmk -f -pdf -output-directory=build -shell-escape ./report.tex

build-presentation:
	@latexmk -f -pdf -output-directory=build -shell-escape ./presentation.tex

clean:
	@rm -rf build

build-with-biblio: build
	@cp ./biblio.bib ./build
	@cd build && biber report
