# SCP-079-WARN - Warn or ban someone by admin commands
# Copyright (C) 2019 SCP-079 <https://scp-079.org>
#
# This file is part of SCP-079-WARN.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging
from time import sleep

from pyrogram import Client

from .. import glovar
from .channel import share_data
from .etc import code, general_link, get_now, lang, thread
from .file import data_to_file, save
from .group import delete_message, leave_group
from .telegram import get_admins, get_group_info, send_message

# Enable logging
logger = logging.getLogger(__name__)


def backup_files(client: Client) -> bool:
    # Backup data files to BACKUP
    try:
        for file in glovar.file_list:
            # Check
            if not eval(f"glovar.{file}"):
                continue

            # Share
            share_data(
                client=client,
                receivers=["BACKUP"],
                action="backup",
                action_type="data",
                data=file,
                file=f"data/{file}"
            )
            sleep(5)

        return True
    except Exception as e:
        logger.warning(f"Backup error: {e}", exc_info=True)

    return False


def interval_hour_01(client: Client) -> bool:
    # Execute every hour
    glovar.locks["message"].acquire()
    try:
        # Clear old calling messages
        now = get_now()
        for gid in list(glovar.message_ids):
            mid, time = glovar.message_ids[gid]

            if not time:
                continue

            if now - time < 86400:
                continue

            glovar.message_ids[gid] = (0, 0)
            delete_message(client, gid, mid)

        save("message_ids")

        # Clear old reports
        now = get_now()
        for key in list(glovar.reports):
            report_record = glovar.reports[key]
            time = report_record["time"]

            if not time:
                glovar.reports.pop(key, {})
                continue

            if now - time < 86400:
                continue

            gid = report_record["group_id"]
            mid = report_record["report_id"]
            thread(delete_message, (client, gid, mid))
            glovar.reports.pop(key, {})

        save("reports")

        # Clear user's waiting status
        for uid in list(glovar.user_ids):
            glovar.user_ids[uid]["waiting"] = set()

        save("user_ids")

        return True
    except Exception as e:
        logger.warning(f"Interval hour 01 error: {e}", exc_info=True)
    finally:
        glovar.locks["message"].release()

    return False


def reset_data(client: Client) -> bool:
    # Reset data every month
    try:
        glovar.bad_ids = {
            "users": set()
        }
        save("bad_ids")

        glovar.left_group_ids = set()
        save("left_group_ids")

        glovar.user_ids = {}
        save("user_ids")

        glovar.watch_ids = {
            "ban": {},
            "delete": {}
        }
        save("watch_ids")

        glovar.reports = {}
        save("reports")

        # Send debug message
        text = (f"{lang('project')}{lang('colon')}{general_link(glovar.project_name, glovar.project_link)}\n"
                f"{lang('action')}{lang('colon')}{code(lang('reset'))}\n")
        thread(send_message, (client, glovar.debug_channel_id, text))

        return True
    except Exception as e:
        logger.warning(f"Reset data error: {e}", exc_info=True)

    return False


def update_admins(client: Client) -> bool:
    # Update admin list every day
    glovar.locks["admin"].acquire()
    try:
        group_list = list(glovar.admin_ids)
        for gid in group_list:
            should_leave = True
            reason = "permissions"
            admin_members = get_admins(client, gid)
            if admin_members and any([admin.user.is_self for admin in admin_members]):
                glovar.admin_ids[gid] = {admin.user.id for admin in admin_members
                                         if ((not admin.user.is_bot and not admin.user.is_deleted)
                                             or admin.user.id in glovar.bot_ids)}
                if glovar.user_id not in glovar.admin_ids[gid]:
                    reason = "user"
                else:
                    for admin in admin_members:
                        if admin.user.is_self:
                            if admin.can_delete_messages and admin.can_restrict_members:
                                should_leave = False

                if should_leave:
                    group_name, group_link = get_group_info(client, gid)
                    share_data(
                        client=client,
                        receivers=["MANAGE"],
                        action="leave",
                        action_type="request",
                        data={
                            "group_id": gid,
                            "group_name": group_name,
                            "group_link": group_link,
                            "reason": reason
                        }
                    )
                    reason = lang(f"reason_{reason}")
                    project_link = general_link(glovar.project_name, glovar.project_link)
                    debug_text = (f"{lang('project')}{lang('colon')}{project_link}\n"
                                  f"{lang('group_name')}{lang('colon')}{general_link(group_name, group_link)}\n"
                                  f"{lang('group_id')}{lang('colon')}{code(gid)}\n"
                                  f"{lang('status')}{lang('colon')}{code(reason)}\n")
                    thread(send_message, (client, glovar.debug_channel_id, debug_text))
                else:
                    save("admin_ids")
            elif admin_members is False or any([admin.user.is_self for admin in admin_members]) is False:
                # Bot is not in the chat, leave automatically without approve
                group_name, group_link = get_group_info(client, gid)
                leave_group(client, gid)
                share_data(
                    client=client,
                    receivers=["MANAGE"],
                    action="leave",
                    action_type="info",
                    data={
                        "group_id": gid,
                        "group_name": group_name,
                        "group_link": group_link
                    }
                )
                project_text = general_link(glovar.project_name, glovar.project_link)
                debug_text = (f"{lang('project')}{lang('colon')}{project_text}\n"
                              f"{lang('group_name')}{lang('colon')}{general_link(group_name, group_link)}\n"
                              f"{lang('group_id')}{lang('colon')}{code(gid)}\n"
                              f"{lang('status')}{lang('colon')}{code(lang('leave_auto'))}\n"
                              f"{lang('reason')}{lang('colon')}{code(lang('reason_leave'))}\n")
                thread(send_message, (client, glovar.debug_channel_id, debug_text))

        return True
    except Exception as e:
        logger.warning(f"Update admin error: {e}", exc_info=True)
    finally:
        glovar.locks["admin"].release()

    return False


def update_report_ids(client: Client) -> bool:
    # Update report group ids
    try:
        report_ids = {gid for gid in list(glovar.configs) if glovar.configs[gid]["report"]["auto"]}
        file = data_to_file(report_ids)
        share_data(
            client=client,
            receivers=["NOSPAM"],
            action="help",
            action_type="list",
            data="report",
            file=file
        )

        return True
    except Exception as e:
        logger.warning(f"Update report ids error: {e}", exc_info=True)

    return False


def update_status(client: Client, the_type: str) -> bool:
    # Update running status to BACKUP
    try:
        share_data(
            client=client,
            receivers=["BACKUP"],
            action="backup",
            action_type="status",
            data={
                "type": the_type,
                "backup": glovar.backup
            }
        )

        return True
    except Exception as e:
        logger.warning(f"Update status error: {e}", exc_info=True)

    return False
