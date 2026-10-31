#!/bin/bash
# Configure the rear-camera pipeline (links + formats) on /dev/media0.
# Idempotent; run after every boot / before streaming.
# Optional: pass "ae" to run the auto-exposure loop afterwards.
P=147258
S() { echo $P | sudo -S "$@" 2>&1; }
M="media-ctl -d /dev/media0"

S modprobe ov13855 >/dev/null 2>&1
S $M -l '"msm_csiphy0":1->"msm_csid0":0[1]'
S $M -l '"msm_csid0":1->"msm_vfe0_rdi0":0[0]'
S $M -l '"msm_csid0":1->"msm_ispif0":0[1]'
S $M -l '"msm_ispif0":1->"msm_vfe0_rdi0":0[1]'
S v4l2-ctl -d /dev/video0 --set-fmt-video=width=4224,height=3136,pixelformat=pgAA >/dev/null
for e in '"ov13855 3-0036":0' '"msm_csiphy0":0' '"msm_csiphy0":1' '"msm_csid0":0' '"msm_csid0":1' '"msm_ispif0":0' '"msm_ispif0":1' '"msm_vfe0_rdi0":0'; do
  S $M -V "$e[fmt:SGRBG10_1X10/4224x3136]" >/dev/null
done

# sensible starting point for a normally lit scene
S v4l2-ctl -d /dev/v4l-subdev17 -c exposure=1200,analogue_gain=400 >/dev/null 2>&1

echo "pipeline configured"

if [ "$1" = "ae" ]; then
  echo "running auto-exposure..."
  S python3 /tmp/pad_ae.py 2>&1 | tail -3
fi