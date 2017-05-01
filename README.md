User bootstrap/editor script for iris.
--

###  Setup

    virtualenv env
    . env/bin/activate
    python setup.py develop


### Usage

First edit your mysql settings in `configs/config.dev.yaml`.


    . env/bin/activate
    make

Then visit http://localhost:16651 in your web browser to view/edit/create/delete iris user accounts.