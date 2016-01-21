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
 * Make sure the queue named is one that has been created already with ```anaconda build queue --create```.  Here the queue should be of form \<user-organization-name\>/\<queue-name\>
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
 * Start the cluster

```
acluster create conda-team-build-worker-linux-64-1 --profile anaconda_builder
```

 * Install more dependencies:

```
acluster ssh
sudo apt-get install m4 make
```
 * Here is how to ssh and su as aworker{X} to inspect or restart chalmers:

```
acluster ssh
ubuntu@ip-172-31-52-162:~$ sudo su - aworker0
aworker0@ip-172-31-52-162:~$ source activate anaconda-builder
(anaconda-builder)aworker0@ip-172-31-52-162:~$ chalmers list
(anaconda-builder)aworker0@ip-172-31-52-162:~$ chalmers restart --all
```

* Here is how to ssh, su and check logs

```
acluster ssh
sudo su - aworker0
source activate anaconda-builder
chalmers log anaconda-build-worker --tail 50
chalmers log anaconda-build-worker --head 50

# show the logfile name
chalmers log anaconda-build-worker —showfile
```

 
## Use the on-demand queue

```
anaconda build submit ./ --queue conda-team/build_recipes_on_demand
```
