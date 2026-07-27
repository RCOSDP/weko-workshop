FROM docker.elastic.co/elasticsearch/elasticsearch:6.8.23
RUN elasticsearch-plugin install --batch analysis-kuromoji && \
    elasticsearch-plugin install --batch analysis-icu
