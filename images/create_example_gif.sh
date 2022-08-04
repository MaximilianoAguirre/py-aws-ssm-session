#!/bin/bash


# https://github.com/asciinema/asciicast2gif
docker run --rm -v $PWD:/data asciinema/asciicast2gif -s 2 -h 30 ./record.json ./example.gif
