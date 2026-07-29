#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shibboleth のユーザ情報とグループ情報を突き合わせて一覧表示する。
List the Shibboleth users side by side with their group membership.

情報が 2 か所に分かれているのでまとめて引く:
  IdP / 属性認証局 … これからログインしたら何が発行されるか (eppn / mail / 職位 / isMemberOf)
                     isMemberOf は WEKO の DB に保存されない (ShibUser.__init__ が読んだあと捨てる)
                     ので、グループを見るにはここに問い合わせるしかない
  WEKO の DB       … 実際にログインした結果 (紐付いた WEKO アカウントと付与済みロール)

The data lives in two places, so both are queried:
  IdP / attribute authority … what a login would issue right now (eppn / mail / affiliation / isMemberOf).
                              isMemberOf is never stored in WEKO's database - ShibUser.__init__ reads it
                              and drops it - so the IdP is the only place to see the groups.
  WEKO's database           … the result of actual logins (the linked WEKO account and granted roles).

Usage:
  python3 list-shib-users.py
  python3 list-shib-users.py --db wekodb --user admin --user teacher
"""
import argparse
import json
import re
import subprocess
import sys

NS = 'weko3'
JSON_RE = re.compile(r'\{.*\}', re.S)


def kubectl(args, check=True):
    r = subprocess.run(['kubectl'] + args, capture_output=True, text=True)
    if check and r.returncode != 0:
        print('ERROR: kubectl %s\n%s' % (' '.join(args), r.stderr.strip()), file=sys.stderr)
        sys.exit(1)
    return r.stdout


def deploy_exists(name):
    r = subprocess.run(['kubectl', '-n', NS, 'get', 'deploy', name],
                       capture_output=True, text=True)
    return r.returncode == 0


def aacli(deploy, principal, requester):
    """IdP 自身の CLI で属性解決だけを行う (ログイン不要)。
    Resolve attributes with the IdP's own CLI - no login involved."""
    out = kubectl(['-n', NS, 'exec', 'deploy/' + deploy, '--', 'sh', '-c',
                   'IDP_BASE_URL=http://localhost:8080/idp; export IDP_BASE_URL; '
                   'cd /opt/shibboleth-idp && bash bin/aacli.sh -n %s -r %s 2>/dev/null'
                   % (principal, requester)], check=False)
    m = JSON_RE.search(out)
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return {}
    return {a['name']: a.get('values', []) for a in data.get('attributes', [])}


def htpasswd_users(deploy):
    out = kubectl(['-n', NS, 'exec', 'deploy/' + deploy, '--', 'sh', '-c',
                   "grep -v '^#' /opt/shibboleth-idp/credentials/demo.htpasswd | cut -d: -f1"])
    return [u.strip() for u in out.splitlines() if u.strip()]


def weko_rows(db):
    """WEKO 側の紐付けとロールを 1 クエリで引く / one query for the WEKO-side links and roles."""
    pgm = kubectl(['get', 'pod', '-n', NS,
                   '-l', 'cluster-name=weko-postgresql,spilo-role=master',
                   '-o', 'jsonpath={.items[0].metadata.name}']).strip()
    sql = ("select s.shib_eppn, u.email, s.shib_user_name, s.shib_role_authority_name, "
           "coalesce(string_agg(r.name, ', ' order by r.name), '') "
           "from shibboleth_user s "
           "join accounts_user u on u.id = s.weko_uid "
           "left join accounts_userrole ur on ur.user_id = u.id "
           "left join accounts_role r on r.id = ur.role_id "
           "group by s.shib_eppn, u.email, s.shib_user_name, s.shib_role_authority_name "
           "order by 1;")
    out = kubectl(['exec', '-n', NS, pgm, '--', 'psql', '-U', 'postgres', '-d', db, '-tAF|', '-c', sql])
    rows = {}
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split('|')
        if len(parts) < 5:
            continue
        rows[parts[0]] = {'email': parts[1], 'user_name': parts[2],
                          'affiliation': parts[3], 'roles': parts[4]}
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--db', default='wekodb', help='テナントの DB 名 / the tenant database name')
    p.add_argument('--tenant-host', default='tenant1.localhost',
                   help='SP の entityID を組み立てるホスト / the host the SP entityID is built from')
    p.add_argument('--user', action='append',
                   help='対象ユーザ (省略時は htpasswd の全員) / users to inspect (default: all in htpasswd)')
    p.add_argument('--table', action='store_true',
                   help='eppn と isMemberOf だけを表形式で出す / print just eppn and isMemberOf as a table')
    p.add_argument('--tsv', action='store_true',
                   help='--table をタブ区切りで (grep/sort 用) / same as --table but tab separated')
    args = p.parse_args()

    requester = 'https://%s/shibboleth-sp' % args.tenant_host
    has_map = deploy_exists('weko-shib-map')
    group_src = 'weko-shib-map' if has_map else 'weko-shib-idp'

    # 表形式: eppn と isMemberOf だけ。グループ 1 つにつき 1 行なので grep / sort しやすい。
    # 属性認証局も eppn を公開しているので、問い合わせは 1 回で足りる。
    # Table form: just eppn and isMemberOf, one row per group so it greps and sorts easily.
    # The attribute authority releases eppn as well, so a single query is enough.
    if args.table or args.tsv:
        users = args.user or htpasswd_users('weko-shib-idp')
        rows = []
        for u in users:
            a = aacli(group_src, u, requester)
            eppn = (a.get('eduPersonPrincipalName') or ['-'])[0]
            for g in a.get('isMemberOf') or ['-']:
                rows.append((eppn, g))
        if args.tsv:
            for e, g in rows:
                print('%s\t%s' % (e, g))
        else:
            w = max([len(e) for e, _ in rows] + [len('eppn')])
            print('%-*s  %s' % (w, 'eppn', 'isMemberOf'))
            print('%-*s  %s' % (w, '-' * w, '-' * 44))
            for e, g in rows:
                print('%-*s  %s' % (w, e, g))
        return

    print('IdP            : weko-shib-idp')
    print('グループの出どころ / groups from : %s%s'
          % (group_src, '' if has_map else '  (WEKO_SHIB_MAP=aggregation ではないため IdP 自身)'))
    print()

    users = args.user or htpasswd_users('weko-shib-idp')
    db = weko_rows(args.db)
    seen_eppn = set()

    for u in users:
        idp = aacli('weko-shib-idp', u, requester)
        grp = aacli(group_src, u, requester) if has_map else idp
        eppn = (idp.get('eduPersonPrincipalName') or ['-'])[0]
        seen_eppn.add(eppn)
        row = db.get(eppn)

        print('== %s ==' % u)
        print('  eppn                   : %s' % eppn)
        print('  mail                   : %s' % (idp.get('mail') or ['-'])[0])
        print('  displayName            : %s' % (idp.get('displayName') or ['-'])[0])
        print('  wekoSocietyAffiliation : %s' % (idp.get('wekoSocietyAffiliation') or ['-'])[0])
        groups = grp.get('isMemberOf') or []
        print('  isMemberOf (%d)         : %s' % (len(groups), groups[0] if groups else '-'))
        for g in groups[1:]:
            print('                           %s' % g)
        if row:
            print('  --- WEKO (ログイン済み / logged in) ---')
            print('  WEKO アカウント        : %s' % row['email'])
            print('  付与済みロール         : %s' % (row['roles'] or '-'))
        else:
            print('  --- WEKO: 未ログイン (紐付けなし) / never logged in ---')
        print()

    # aacli は 1 回あたり数秒かかるので、ループ中に集めた eppn を使い回す
    # aacli takes a few seconds per call, so reuse the eppns gathered in the loop above
    extra = [e for e in db if e not in seen_eppn]
    if extra:
        print('== htpasswd に無いが WEKO に残っている紐付け / linked in WEKO but not in htpasswd ==')
        for e in extra:
            print('  %-24s %-24s %s' % (e, db[e]['email'], db[e]['roles']))


if __name__ == '__main__':
    main()
