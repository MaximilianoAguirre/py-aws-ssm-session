#!/bin/bash

docker run --rm -v $PWD:/data asciinema/asciicast2gif -s 2 -h 30 ./record.json ./example.gif
