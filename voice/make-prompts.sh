#!/usr/bin/env bash
# Regenerate the call prompts as 8 kHz mono WAV (what Asterisk plays on a phone call).
# Demo: macOS's built-in voice, generated locally. On the GB10, Piper does the same job:
#   echo "$text" | piper --model en_US-lessac-medium.onnx --output_file x.wav && sox x.wav -r 8000 -c 1 out.wav
set -euo pipefail
cd "$(dirname "$0")/prompts"
say_wav() { say -v Samantha -r 175 -o "$1.wav" --file-format=WAVE --data-format=LEI16@8000 "$2"; }
say_wav greeting "Hello, this is the accounts payable verification line for Valley Unified School District. This call is recorded for payment verification."
say_wav q1 "We received a request to change the bank account we pay for Acme School Supply. Did your company send this request? Please answer after the tone."
say_wav q2 "Please tell us the last four digits of the bank account you want us to pay. Please answer after the tone."
say_wav goodbye "Thank you. No payment will change until our team confirms. Goodbye."
ls -l *.wav
