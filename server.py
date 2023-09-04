import argparse
import asyncio
import json
import logging
import os
import ssl
import uuid

import cv2
import datetime
import aiohttp_cors
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from aiortc.contrib.media import MediaBlackhole, MediaPlayer, MediaRecorder, MediaRelay
from aiortc.sdp import candidate_from_sdp
from av import VideoFrame
from aiortc.contrib.signaling import object_from_string
from collections import defaultdict


ROOT = os.path.dirname(__file__)

logger = logging.getLogger("pc")
pcs = {}
orphan_candidate = defaultdict(lambda :[])
relay = MediaRelay()



class MyVideoStreamTrack(VideoStreamTrack):
    def __init__(self):
        super().__init__()
        self.cap = cv2.VideoCapture("rtsp://admin:aidkr1120!@pigrienpam1-1.mycam.to:551/ch1/stream1")
        
    async def recv(self):
        pts, time_base = await self.next_timestamp()
        timenow = str(datetime.datetime.now())
        #print({"pts": pts, "time_base": time_base, "time": timenow})
        image = cv2.imread("test.png")
        cv2.putText(image, timenow, (100, 100), cv2.FONT_HERSHEY_SIMPLEX, 4, (255, 255, 255), 3)
        frame = VideoFrame.from_ndarray(image, format="bgr24")
        frame.pts = pts
        frame.time_base = time_base
        return frame

async def signaling(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
    
    pc = RTCPeerConnection()
    pc_id = params['id']
    pc.client_id = pc_id
    pcs[pc.client_id] = pc

    pc.emit("connectionstatechange", on_connectionstatechange(pc))
    pc.emit("track", add_track(pc))

    await pc.setRemoteDescription(offer)

    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    [pc.addIceCandidate(ice) for ice in orphan_candidate[pc_id]]    

    return web.Response(
        content_type="application/json",
        text=json.dumps(
            {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
        ),
    )

def add_track(pc):
    pc.addTrack(MyVideoStreamTrack())

async def on_connectionstatechange(pc):
        if pc.connectionState == "failed":
            await pc.close()
            del pcs[pc.client_id]

async def ice_negotiation(request):
    try:
        params = await request.json()
        print({"ice_sdp": params})
        
        pc_id = params['id']

        candidate_sdp = params['candidate'].replace('candidate:', '')

        ice = candidate_from_sdp(candidate_sdp)
        ice.sdpMid = params["sdpMid"]
        ice.sdpMLineIndex = params["sdpMLineIndex"]
        print(ice)

        pc = pcs[pc_id]
        await pc.addIceCandidate(ice)

        return web.Response(
            content_type="application/json",
            text=json.dumps({"status": "ok"})
        )
    except KeyError:
        orphan_candidate[pc_id].append(ice)



async def on_shutdown(app):
    # close peer connections
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()
   

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="WebRTC audio / video / data-channels demo"
    )
    parser.add_argument("--cert-file", help="SSL certificate file (for HTTPS)")
    parser.add_argument("--key-file", help="SSL key file (for HTTPS)")
    parser.add_argument(
        "--host", default="0.0.0.0", help="Host for HTTP server (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port", type=int, default=8018, help="Port for HTTP server (default: 8080)"
    )
    parser.add_argument("--record-to", help="Write received media to a file."),
    parser.add_argument("--verbose", "-v", action="count")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    if args.cert_file:
        ssl_context = ssl.SSLContext()
        ssl_context.load_cert_chain(args.cert_file, args.key_file)
    else:
        ssl_context = None

    app = web.Application()

    app.on_shutdown.append(on_shutdown)
    app.router.add_post("/offer", signaling)
    app.router.add_post("/ice", ice_negotiation)

    cors = aiohttp_cors.setup(app, defaults={
            "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*"
        )
    })

    for route in list(app.router.routes()):
        cors.add(route)

    web.run_app(
        app, access_log=None, host=args.host, port=args.port, ssl_context=ssl_context
    )
