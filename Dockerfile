FROM python:3.15-trixie

ADD src/ /app
EXPOSE 5000
WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

CMD ["python", "run.py"]