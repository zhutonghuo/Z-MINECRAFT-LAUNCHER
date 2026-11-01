import sys,time
for i in range(5):
    sys.stdout.write("flushed line %d
" % i); sys.stdout.flush()
    time.sleep(0.4)
