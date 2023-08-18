FROM python:3.9.17

RUN apt-get upgrade -y 
RUN apt-get update -y
RUN apt-get install -y libavdevice-dev libavfilter-dev libopus-dev libvpx-dev pkg-config libsrtp2-dev

RUN pip install aiohttp aiortc opencv-python aiohttp_cors

WORKDIR /home/docker/code
COPY . /home/docker/code/

CMD ["python", "server.py"]