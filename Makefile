all: serve

serve:
	gunicorn --reload --access-logfile=- -b '0.0.0.0:16651' --worker-class gevent \
		-e CONFIG=./configs/config.dev.yaml -e STATIC_ROOT=. iris_admin.gunicorn:application 
