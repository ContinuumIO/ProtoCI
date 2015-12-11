# Steps for starting linux build worker using anaconda-cluster

 * First create an anaconda.org auth token:

```
anaconda auth --create -n "build-recipes-on-demand-linux-64" --scopes "api:build-worker" --out ~/.anac\
onda.token
```

 * Cat that token file and copy the token to the  ~/.acluster/profiles.d/anaconda_builders.yaml file, as shown below

```
cat ~/.anaconda.token
```

* Create a key pair, or get this specific one from me, download it and chmod on it.
 
```
chmod 0600 ~/conda-team-dev.pem
```
 * Make sure your ~/.acluster/providers.yaml has your AWS secret id and key, as well as the name of the key pair and its path (private_key) on your system.

```
$ cat ~/.acluster/providers.yaml
aws_east_anaconda_builder:
  cloud_provider: ec2
  keyname: conda-team-dev
  location: us-east-1
  private_key: ~/conda-team-dev.pem
  secret_id: XXXXX
  secret_key: XXXXX
```

 * Make sure you have a profile in your ~/.acluster/profiles.d that looks like this:
 * Note the token in the yaml below comes from the ```anaconda auth``` step above
 * Make sure the provider: name matches that in your providers.yaml
```
$ cat ~/.acluster/profiles.d/anaconda_builders.yaml
name: anaconda_builder
provider: aws_east_anaconda_builder
num_nodes: 1
node_id: ami-08faa660
node_type: m1.medium
user: ubuntu
conda_channels:
  - anaconda-cluster-contrib
  - anaconda-cluster
  - defaults
head:
  roles:
    - anaconda-builder
data:
  anaconda_builder:
    token: ps-c895b15d-bc0f-41c6-8439-e581b54b0175
    queue: conda-team/build_recipes_on_demand
```

 * Install 1 more dependency:

```
acluster ssh
sudo apt-get install m4
```

## Use the on-demand queue

```
anaconda build submit ./ --queue conda-team/build_recipes_on_demand
```
