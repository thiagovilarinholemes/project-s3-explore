# 📌 S3 Explore
[![License](https://img.shields.io/badge/license-MIT-green.svg)](https://github.com/thiagovilarinholemes/project-s3-explore/blob/main/LICENSE)
![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python)
[![Status](https://img.shields.io/badge/Status-Concluído-green.svg)]()

<img src="docs/01.png">

---

## 🎯 Objetivos 

Diante da necessidade de tornar o processo de desenvolvimento mais ágil e eficiente, foi proposta a criação de uma **interface gráfica para gerenciamento do emulador S3 LocalStack**. A solução tem como objetivo facilitar a visualização, organização e manipulação dos recursos armazenados no ambiente S3, reduzindo a dependência de comandos via terminal e proporcionando uma experiência mais intuitiva durante o desenvolvimento e os testes da aplicação.

---

## 📁 Estrutura considerada

A estrutura utilizada como referência é:

```text
s3_explore/
│
├── backend/
│   └── main.py
│
├── frontend/
│   └── index.html
│
├── Dockerfile
│
├── docker-compose.yml
│
├── requirements.txt
│
└── README.md
```

---

## 🪣 LocalStack

O serviço LocalStack possui as seguintes configurações:
```yaml
localstack:
  image: localstack/localstack:latest
  container_name: electoral-localstack
  ports:
    - "4566:4566"
  environment:
    - PERSISTENCE=1
  volumes:
    - localstack_data:/var/lib/localstack
  networks:
    - electoral-network
```

O endpoint utilizado pelo Explorer é:
```yaml
http://localstack:4566
```

---

## 🌐 S3 Explorer

A configuração para o serviço é:

```yaml
s3-explorer:
  image: s3-explorer:latest
  container_name: electoral-s3-explorer
  ports:
    - "8090:8003"
  environment:
    - S3_ENDPOINT_URL=http://localstack:4566
    - AWS_ACCESS_KEY_ID=test
    - AWS_SECRET_ACCESS_KEY=test
    - AWS_DEFAULT_REGION=us-east-1
  depends_on:
    - localstack
  networks:
    - electoral-network
```

A interface é acessada em:
```yaml
http://localhost:8090
```
---

## 👨‍💻 Autor

**Thiago Vilarinho Lemes**\
💻 Engenheiro e Analista de Dados.\
🏠 Home: https://thiagolemes.netlify.app/ \
🔗 LinkedIn: <a href="https://www.linkedin.com/in/thiago-v-lemes-b1232727" target="_blank">Thiago Lemes</a><br>
✉️ e-mail:contatothiagolemes@gmail.com | lemes_vilarinho@yahoo.com.br


Principais áreas:

```text
Data Engineering
Docker
Kafka
Python
SQL
Apache Airflow
Docker
PostgreSQL
Data Lake
ETL
APIs
Cloud
IoT
Machine Learning
Generative AI
```