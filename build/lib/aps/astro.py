# Used same definitions used in Fortran code to have same precision
PI__NUM = 3.141592653589793
RAD__TO__MAS = 3600.0 * 1000.0 * 180.0 / PI__NUM
RAD__TO__MSEC = RAD__TO__MAS / 15.0
MAS__TO__RAD = PI__NUM / (3600.0 * 180.0 * 1000.0)
RAD__TO__MSEC = RAD__TO__MAS / 15.0
MSEC__TO__RAD = MAS__TO__RAD * 15.0
OM__EAR = 7.292115146706979e-05  # rad/sec

