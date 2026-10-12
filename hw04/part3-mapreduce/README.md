# HW4 Part III – Mini MapReduce word count on ECS + S3

## Design
One Go worker image (`worker/`) exposes all three roles over HTTP on port 8080:

| Endpoint | Role | What it does |
|---|---|---|
| `GET /split?url=s3://b/k&n=3` | Splitter | Reads the input from S3, cuts it into `n` byte-balanced chunks (cut points moved to the next non-word byte so no word is split), writes `jobs/<id>/chunks/chunk-NNN.txt`, returns the chunk URLs. |
| `GET /map?url=s3://b/chunk` | Mapper | Counts words in one chunk, writes `jobs/<id>/maps/chunk-NNN.json`, returns its URL. |
| `GET /reduce?urls=a,b,c` | Reducer | Merges the mapper JSON files, writes `jobs/<id>/final.json`, returns its URL. |

Every ECS task runs the same image; `driver.py` assigns roles (first IP = splitter,
last = reducer, the rest = mappers), calls the mappers in parallel, times each stage
and verifies the final JSON against a local single-process count.
A word = maximal run of ASCII letters/digits, lowercased (same rule in Go and Python).

Tasks use **LabRole** as the task role, which gives them S3 access without keys.

## Files
- `worker/` – Go service + Dockerfile
- `deploy.sh` – build linux/amd64 image, push to ECR repo `mapreduce-worker`
- `run-tasks.sh N` – register task definition, start N Fargate tasks, write `ips.txt`
- `driver.py` – run and verify one job
- `experiment.py` – sweep input sizes × mapper counts, write `results/*.csv`
- `plot.py` – make the plots in `results/`
- `stop-tasks.sh` – stop the worker tasks; `cleanup.sh` – delete all HW4 resources

## Run
```bash
bash deploy.sh
BUCKET=mapreduce-nikhil-$(date +%s); aws s3 mb s3://$BUCKET --region us-west-2; echo $BUCKET > bucket.txt
aws s3 cp data/input.txt s3://$BUCKET/inputs/input.txt
bash run-tasks.sh 5
python3 driver.py --input s3://$BUCKET/inputs/input.txt --local data/input.txt
python3 experiment.py --bucket $BUCKET
python3 plot.py
bash stop-tasks.sh
```
