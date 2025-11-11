pdflatex structure.tex
convert -density 300 structure.pdf -quality 100 talkpipe_diagram.png
rm structure.pdf

pdflatex talkpipe_architecture.tex
convert -density 300 talkpipe_architecture.pdf -quality 100 talkpipe_architecture.png
rm talkpipe_architecture.pdf