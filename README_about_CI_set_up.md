
## Setting up continuous integration on your fork of conda-recipes

 * CI is already set up on conda/conda-recipes main repo, but it is not set up on your fork yet unless you do it.
 * Here are the steps you need to do:
   
```
conda install anaconda-client anaconda-build
anaconda login  # interactive login to anaconda.org

anaconda package --create my_username/conda-recipes   # replacing my_username with your anaconda.org username

```
 * Navigate in anaconda.org to https://anaconda.org/my_username/conda-recipes
 * From there go to Settings -> Continuous Integration
 * Make the following entries in the Continuous Integration set up form:
  * Change the owner/repository, like PeterDSteinberg/conda-recipes
  * Make sure 'webhook' is checked
  * You probably want to test all branches, so leave the tested branch at /refs/heads/.*
  * Leave all else at defaults, except:
   * Change Build Queue to `conda-team/build_recipes`
   * Enter your email address for build notifications
  

After those steps, do a push to your conda-recipes fork, and then check your builds at:

```
https://anaconda.org/my_username/conda-recipes
```
When your branch is merged into the main conda/conda-recipes repo, you should be able to find a build at that time in:

```
https://anaconda.org/conda-team/conda-recipes
```
