FROM python:3.10-bullseye

RUN apt update && apt upgrade -y

ADD src/ /app
EXPOSE 5000
WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

CMD ["python", "run.py"]