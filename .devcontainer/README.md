# Devcontainer Template
Devcontainers allow interactive development inside of a docker container using VSCode. 


This devcontainer creates a reproducible environment for python projects using micromamba    
environments (faster/more robust version of conda). To add this devcontainer template to your project, copy this .devcontainer folder  
into the parent directory of your repository, and copy this [.gitattributes file](https://github.com/Michael-Baker-International-Lakewood/mbi_templates/blob/main/.gitattributes) into the same parent directory.

When opening this repository in VSCode, you may be prompted to re-open the project in devcontainer.  
Alternatively, you may access this option through the  
View menu -> Command Palette -> DevContainers: Reopen in Container.

Other requirements:
1. An environment file (env.yaml) is required placed in the root folder of the  
project for a reproducible python environment to be succussfully built.
2. docker installed on the local machine (linux)
