# Central SeaweedFS configuration for Kanoon

Kanoon does not run its own object-storage container. Its data plane connects to the central
SeaweedFS S3 gateway over the private service network and signs browser requests against a separate
public HTTPS endpoint.

## 1. Add the Kanoon identity

Copy the identity from `s3-config.example.json` into the `identities` array of the central
SeaweedFS S3 configuration. Do not replace the file if it already contains identities for other
projects. Replace both credential placeholders with independently generated values and put the same
values in Kanoon's `KANOON_S3_ACCESS_KEY` and `KANOON_S3_SECRET_KEY` secrets.

The runtime identity is limited to `Read`, `List`, and `Write` for the `kanoon` bucket.
It deliberately has no cross-bucket or `Admin` permission. Create the bucket separately with a
central storage administrator identity before starting Kanoon.

If the central installation manages identities dynamically, the equivalent `weed shell` command is:

```text
s3.configure -access_key=REPLACE_WITH_KANOON_ACCESS_KEY -secret_key=REPLACE_WITH_KANOON_SECRET_KEY -buckets=kanoon -user=kanoon-backend -actions=Read,List,Write -apply
```

Start the gateway with its existing configuration path, for example:

```bash
weed s3 \
  -filer=127.0.0.1:8888 \
  -port=8333 \
  -config=/etc/seaweedfs/s3.json \
  -allowedOrigins=https://kanoon.esaminu.ir
```

If this shared gateway serves browser traffic for several projects, provide their exact origins as
a comma-separated list. Never retain SeaweedFS's permissive `*` default for a credentialed shared
gateway. SeaweedFS can reload the static S3 identity configuration on `SIGHUP`.

## 2. Create the bucket and apply CORS

Using a central storage administrator credential, create the bucket if it does not exist:

```bash
aws --endpoint-url http://storage.abhp.internal:8333 \
  s3api create-bucket --bucket kanoon
```

For SeaweedFS versions supporting S3 bucket CORS, copy `cors-kanoon.example.json` to the server and
apply it:

```bash
aws --endpoint-url http://storage.abhp.internal:8333 \
  s3api put-bucket-cors \
  --bucket kanoon \
  --cors-configuration file:///etc/seaweedfs/cors-kanoon.json
```

The gateway-level `-allowedOrigins` setting remains required as the outer allowlist. Add an admin
frontend origin to both configurations only if that frontend directly uploads to S3. Localhost
origins should be temporary and must not be enabled on the production shared gateway.

## 3. Expose the public endpoint

Use `Caddyfile.example` as a template. Create public DNS and TLS for the chosen hostname. The proxy
must preserve the original Host, path, query string, method, and request body because they are bound
to the S3 signature. Do not expose the filer, master, or volume-server ports publicly.

## 4. Configure Kanoon

```dotenv
KANOON_S3_ENDPOINT_URL=http://storage.abhp.internal:8333
KANOON_S3_PUBLIC_ENDPOINT_URL=https://storage.example.com
KANOON_S3_BUCKET=kanoon
KANOON_S3_ACCESS_KEY=<same access key as the SeaweedFS identity>
KANOON_S3_SECRET_KEY=<same secret key as the SeaweedFS identity>
```

Then recreate the data-plane container so Compose reads the new environment:

```bash
docker compose up -d --build --force-recreate backend
```
