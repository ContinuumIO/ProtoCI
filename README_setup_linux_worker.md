# Setup a linux worker

#### Update Linux

```
sudo yum -y update
```

#### Create anaconda user

```
sudo useradd -s /bin/bash -m -d /home/anaconda anaconda
sudo passwd anaconda

 # Set password
sudo su - anaconda # verify this works
```

#### Install Build Dependancies as root

```
sudo yum install -y ntp chrpath wget dos2unix gcc gcc-c++ git m4
```

#### As anaconda User

```
sudo su - anaconda
```
#### Install Miniconda

```
wget http://repo.continuum.io/miniconda/Miniconda-latest-Linux-x86_64.sh
bash Miniconda-latest-Linux-x86_64.sh
```

#### Make sure to make miniconda install on the path

```
source .bashrc
```

#### Update conda

```
conda update conda
```

#### Install base stuff

```
conda install anaconda-client
conda install anaconda-build
conda install -n root conda-build
```

#### Install additional stuff

```
conda install ndg-httpsclient
conda install jinja2
```

#### Create Worker Directory

```
mkdir worker
```

#### Start anaconda build worker

 * Create authorization token

```
anaconda auth --create -n "conda-team-build-linux-64" --scopes "api:build-worker" --out ~/.conda-team-build.token
```

 * Log out of anaconda

```
anaconda logout
```

#### Install Chalmers and Add to Build Queue

```
conda install chalmers

anaconda worker register -p linux-64 --dist aws-linux --hostname $(hostname -f) conda-team/build_recipes
# prints out a worker_id to use in the next step
```


```
chalmers add --name anaconda-build-worker -c "anaconda --show-traceback -t /home/anaconda/.conda-team-build.token worker run 56686922ea546b0acd9ce187 --status-file /home/anaconda/worker/worker.status"
```


```
chalmers start --all
```


#### Forgot something
 * Do your forgotten commands, then restart chalmers:
```
chalmers restart --all
```
#### Issues with chalmers

* Check the log if you have any issues using

```
chalmers log anaconda-build-worker
```

 * If you need to update the script

```
export EDITOR=vim - chalmers edit anaconda-build-worker
```
