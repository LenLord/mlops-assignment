#!/bin/bash
ssh -L 3000:localhost:3000 -L 9090:localhost:9090 -L 3001:localhost:3001 -L 8000:localhost:8000 -L 8001:localhost:8001 lenlord2@195.242.30.120
