all: serve

serve:
	gunicorn --reload --access-logfile=- -b '0.0.0.0:16651' --worker-class gevent \
		-e CONFIG=./configs/config.dev.yaml iris_admin.gunicorn:application
