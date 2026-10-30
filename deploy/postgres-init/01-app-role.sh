#!/bin/bash
# İlk açılışta: uygulama için süper yetkisiz bir sahip kullanıcı ve veritabanı.
# API bu kullanıcıyla bağlanır; RLS'i atlayabilecek süper kullanıcıyla değil.
set -euo pipefail
psql -v ON_ERROR_STOP=1 --username postgres <<SQL
create role "${APP_DB_USER}" login createrole password '${APP_DB_PASSWORD}';
create database "${APP_DB_NAME}" owner "${APP_DB_USER}";
revoke all on database "${APP_DB_NAME}" from public;
SQL
