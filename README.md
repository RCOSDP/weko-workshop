# Introduction

## Basis of WEKO3

WEKO3 is open-source software for building repositories. It was developed using the Invenio3 framework, which is also open-source software.

WEKO3 provides the functionality needed to build repositories. For easy operation, many functions are available via a web browser.

WEKO3 distinguishes the expected users by the following roles: First, non-logged-in users. This user can perform basic operations such as searching and viewing the repository. Next is the logged-in user. This user can register articles and research data in the repository. Next is "Community Administrator". This user can manage a part of the repository. Next is "Repository Administrator". This user can change repository settings, metadata format, design, etc. Last is "System Administrator". The system administrator is a user who can control and configure repository system functions.

In WEKO3, the registration unit of a repository is called an item. An item consists of a content file and a set of metadata. There may be no content file.

The metadata of an item is defined by a schema called item type. An item type consists of several properties, including properties such as title and creator.

Item registration is performed using "Workflows," which are pairs of "Flow" that define registration procedures and "Item Type" to be registered in those flows. An instance of a workflow is called an "Activity". A user who has the authority to register items in the repository invokes an "Activity" to register items in the repository.

Now we will start the [WEKO3 workshop](./SUMMARY.md).
