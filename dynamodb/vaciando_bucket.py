import boto3

s3 = boto3.resource('s3')
bucket = s3.Bucket("miu-documentos")

def vaciar_bucket(bucket):
    bucket.object_versions.delete()  # incluye versiones y delete markers
    print("Bucket vacío completamente.")

vaciar_bucket(bucket)
