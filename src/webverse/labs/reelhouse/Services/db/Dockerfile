FROM mysql:8.0
COPY conf.d/lowmem.cnf /etc/mysql/conf.d/lowmem.cnf
RUN chmod 644 /etc/mysql/conf.d/lowmem.cnf
CMD ["mysqld", "--default-authentication-plugin=mysql_native_password"]