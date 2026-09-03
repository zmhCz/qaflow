from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('data_factory', '0005_alter_businessloadtask_scenario_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='businessloadtask',
            name='scenario_type',
            field=models.CharField(
                choices=[
                    ('room_list_load', '房间列表压测'),
                    ('voice_room_online', '语音房在线保活'),
                    ('room_enter_leave', '进退房压测'),
                    ('community_follow', '关注社区压测'),
                    ('community_activity_simulation', '社区活跃模拟'),
                    ('im_message_flood', 'IM 消息刷屏压测'),
                    ('team_recruit_publish', '发布组队压测'),
                ],
                max_length=64,
                verbose_name='场景类型',
            ),
        ),
    ]
